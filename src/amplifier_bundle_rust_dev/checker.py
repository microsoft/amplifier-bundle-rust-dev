"""Core Rust checking logic.

This module contains all the checking logic, shared by:
- Tool module (rust_check tool for agents)
- Hook module (automatic checks on file events)
"""

import json
import re
import subprocess
from pathlib import Path

from .config import load_config
from .models import CheckConfig
from .models import CheckResult
from .models import Issue
from .models import Severity


class RustChecker:
    """Main checker that orchestrates cargo fmt, clippy, cargo check, and stub detection."""

    def __init__(
        self,
        config: CheckConfig | None = None,
        workspace_root: str | Path | None = None,
    ):
        """Initialize checker with optional config."""
        self.config = config or load_config()
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()

    def check_files(self, paths: list[str | Path]) -> CheckResult:
        """Run all enabled checks on the given paths.

        For cargo commands, paths are passed as package/workspace arguments.
        For stub detection, paths are scanned directly for .rs files.

        Args:
            paths: Files or directories to check

        Returns:
            CheckResult with all issues found
        """
        if not paths:
            paths = [Path.cwd()]

        path_strs = [str(p) for p in paths]
        results = CheckResult(files_checked=self._count_rust_files(path_strs))

        cargo_enabled = self.config.enable_cargo_fmt or self.config.enable_clippy or self.config.enable_cargo_check
        cargo_root = None
        if cargo_enabled:
            if not self.config.allow_workspace_execution:
                results = results.merge(self._execution_blocked_result())
            else:
                cargo_root, validation_result = self._resolve_cargo_root(path_strs)
                if validation_result:
                    results = results.merge(validation_result)

        if cargo_root is not None:
            if self.config.enable_cargo_fmt:
                fmt_result = self._run_cargo_fmt(cargo_root)
                results = results.merge(fmt_result)

            if self.config.enable_clippy:
                clippy_result = self._run_clippy(cargo_root)
                results = results.merge(clippy_result)

            if self.config.enable_cargo_check:
                check_result = self._run_cargo_check(cargo_root)
                results = results.merge(check_result)

        if self.config.enable_stub_check:
            stub_result = self._run_stub_check(path_strs)
            results = results.merge(stub_result)

        return results

    def _execution_blocked_result(self) -> CheckResult:
        """Report that execution-capable checks were skipped."""
        return CheckResult(
            issues=[
                Issue(
                    file=str(self.workspace_root),
                    line=0,
                    column=0,
                    code="WORKSPACE-UNTRUSTED",
                    message=(
                        "Skipped Cargo-based checks because they can execute build.rs, "
                        "procedural macros, dependencies, and external tools"
                    ),
                    severity=Severity.WARNING,
                    source="trust-policy",
                    suggestion=(
                        "Enable allow_workspace_execution only in host-controlled "
                        "configuration after trusting the workspace and toolchain"
                    ),
                )
            ],
            checks_run=["cargo-skipped-untrusted"],
        )

    def _resolve_cargo_root(self, paths: list[str]) -> tuple[Path | None, CheckResult | None]:
        """Validate paths and return the canonical Cargo root for execution."""
        cargo_toml = self._find_cargo_toml(self.workspace_root)
        if cargo_toml is None:
            return None, self._workspace_error(
                "CARGO-WORKSPACE-NOT-FOUND",
                f"No Cargo.toml found at or above {self.workspace_root}",
            )

        cargo_root = cargo_toml.parent.resolve()
        for path_str in paths:
            candidate = Path(path_str)
            if not candidate.is_absolute():
                candidate = self.workspace_root / candidate
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(cargo_root)
            except (OSError, ValueError):
                return None, self._workspace_error(
                    "PATH-OUTSIDE-WORKSPACE",
                    f"Refusing Cargo execution for path outside {cargo_root}: {path_str}",
                )

        return cargo_root, None

    @staticmethod
    def _find_cargo_toml(start_path: Path) -> Path | None:
        """Find Cargo.toml by walking up from a canonical directory."""
        current = start_path if start_path.is_dir() else start_path.parent
        while True:
            candidate = current / "Cargo.toml"
            if candidate.is_file():
                return candidate
            if current == current.parent:
                return None
            current = current.parent

    def _workspace_error(self, code: str, message: str) -> CheckResult:
        """Create an explicit workspace-validation error."""
        return CheckResult(
            issues=[
                Issue(
                    file=str(self.workspace_root),
                    line=0,
                    column=0,
                    code=code,
                    message=message,
                    severity=Severity.ERROR,
                    source="trust-policy",
                )
            ],
            checks_run=["cargo-workspace-validation"],
        )

    def _count_rust_files(self, paths: list[str]) -> int:
        """Count Rust files in the given paths."""
        count = 0
        for path_str in paths:
            path = Path(path_str)
            if path.is_file() and path.suffix == ".rs":
                count += 1
            elif path.is_dir():
                count += len(list(path.rglob("*.rs")))
        return count

    # ── Cargo fmt ──────────────────────────────────────────────

    def _run_cargo_fmt(self, cargo_root: Path) -> CheckResult:
        """Run cargo fmt --check."""
        cmd = ["cargo", "fmt", "--check"]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=cargo_root, check=False)
        except FileNotFoundError:
            return CheckResult(
                issues=[
                    Issue(
                        file="",
                        line=0,
                        column=0,
                        code="TOOL-NOT-FOUND",
                        message="cargo not found. Install Rust from https://rustup.rs",
                        severity=Severity.ERROR,
                        source="cargo-fmt",
                    )
                ],
                checks_run=["cargo-fmt"],
            )

        return self._parse_cargo_fmt_output(result.stdout if result.returncode != 0 else "")

    def _parse_cargo_fmt_output(self, output: str) -> CheckResult:
        """Parse cargo fmt --check diff-style output.

        Format: 'Diff in /path/to/file.rs at line N:' followed by diff lines.
        """
        issues = []

        if output.strip():
            # Match lines like: "Diff in /path/to/file.rs at line 5:"
            for match in re.finditer(r"Diff in (.+?) at line (\d+):", output):
                file_path = match.group(1)
                line_num = int(match.group(2))
                issues.append(
                    Issue(
                        file=file_path,
                        line=line_num,
                        column=1,
                        code="FORMAT",
                        message="File needs formatting",
                        severity=Severity.WARNING,
                        source="cargo-fmt",
                        suggestion="Run `cargo fmt` to auto-format",
                    )
                )

        return CheckResult(issues=issues, checks_run=["cargo-fmt"])

    # ── Clippy ─────────────────────────────────────────────────

    def _run_clippy(self, cargo_root: Path) -> CheckResult:
        """Run cargo clippy with JSON output."""
        cmd = [
            "cargo",
            "clippy",
            "--message-format=json",
            "--",
            "-W",
            "clippy::all",
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=cargo_root, check=False)
        except FileNotFoundError:
            return CheckResult(
                issues=[
                    Issue(
                        file="",
                        line=0,
                        column=0,
                        code="TOOL-NOT-FOUND",
                        message="cargo not found. Install Rust from https://rustup.rs",
                        severity=Severity.ERROR,
                        source="clippy",
                    )
                ],
                checks_run=["clippy"],
            )

        return self._parse_cargo_json_output(result.stdout, source="clippy")

    # ── Cargo check ────────────────────────────────────────────

    def _run_cargo_check(self, cargo_root: Path) -> CheckResult:
        """Run cargo check with JSON output."""
        cmd = ["cargo", "check", "--message-format=json"]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=cargo_root, check=False)
        except FileNotFoundError:
            return CheckResult(
                issues=[
                    Issue(
                        file="",
                        line=0,
                        column=0,
                        code="TOOL-NOT-FOUND",
                        message="cargo not found. Install Rust from https://rustup.rs",
                        severity=Severity.ERROR,
                        source="cargo-check",
                    )
                ],
                checks_run=["cargo-check"],
            )

        return self._parse_cargo_json_output(result.stdout, source="cargo-check")

    # ── Shared JSON parser for clippy and cargo check ──────────

    def _parse_cargo_json_output(self, output: str, source: str) -> CheckResult:
        """Parse JSON lines output from cargo clippy or cargo check.

        Cargo emits one JSON object per line. We only care about objects with
        "reason": "compiler-message". Each has a "message" object containing
        level, code, spans, and the human-readable message.

        Args:
            output: Raw stdout from cargo command (JSON lines)
            source: Source label ("clippy" or "cargo-check")

        Returns:
            CheckResult with parsed issues
        """
        issues = []

        if not output.strip():
            return CheckResult(issues=[], checks_run=[source])

        for line in output.strip().split("\n"):
            line = line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Only process compiler-message entries
            if obj.get("reason") != "compiler-message":
                continue

            msg = obj.get("message", {})
            level = msg.get("level", "")

            # Map cargo levels to our Severity
            if level == "error":
                severity = Severity.ERROR
            elif level == "warning":
                severity = Severity.WARNING
            elif level in ("note", "help"):
                severity = Severity.INFO
            else:
                continue  # Skip unknown levels

            # Get the code (e.g., "E0308" or "clippy::needless_return")
            code_obj = msg.get("code")
            code = code_obj.get("code", "") if code_obj else ""

            # Get file location from the primary span
            spans = msg.get("spans", [])
            primary_span = next((s for s in spans if s.get("is_primary")), None)

            file_name = ""
            line_start = 0
            col_start = 0
            line_end = None
            col_end = None

            if primary_span:
                file_name = primary_span.get("file_name", "")
                line_start = primary_span.get("line_start", 0)
                col_start = primary_span.get("column_start", 0)
                line_end = primary_span.get("line_end")
                col_end = primary_span.get("column_end")

            issues.append(
                Issue(
                    file=file_name,
                    line=line_start,
                    column=col_start,
                    code=code,
                    message=msg.get("message", ""),
                    severity=severity,
                    source=source,
                    end_line=line_end,
                    end_column=col_end,
                )
            )

        return CheckResult(issues=issues, checks_run=[source])

    # ── Stub detection ─────────────────────────────────────────

    def _run_stub_check(self, paths: list[str]) -> CheckResult:
        """Check for TODOs, stubs, and placeholder code in .rs files."""
        issues = []

        for path_str in paths:
            path = Path(path_str)
            if path.is_file() and path.suffix == ".rs":
                issues.extend(self._check_file_for_stubs(path))
            elif path.is_dir():
                for rs_file in path.rglob("*.rs"):
                    if self._should_exclude(rs_file):
                        continue
                    issues.extend(self._check_file_for_stubs(rs_file))

        return CheckResult(issues=issues, checks_run=["stub-check"])

    def _should_exclude(self, path: Path) -> bool:
        """Check if path matches any exclude pattern."""
        path_str = str(path)
        for pattern in self.config.exclude_patterns:
            if pattern.endswith("/**"):
                dir_pattern = pattern[:-3]
                if dir_pattern in path_str:
                    return True
            elif pattern in path_str:
                return True
        return False

    def _check_file_for_stubs(self, file_path: Path) -> list[Issue]:
        """Check a single .rs file for stub patterns."""
        issues = []

        try:
            content = file_path.read_text(encoding="utf-8")
            lines = content.split("\n")
        except Exception:
            return issues

        # Test files are entirely exempt
        if self._is_test_file(file_path):
            return issues

        for line_num, line in enumerate(lines, 1):
            for pattern, description, is_macro in self.config.stub_patterns:
                if re.search(pattern, line):
                    # Check for legitimate exemptions
                    if self._is_legitimate_rust_pattern(file_path, line_num, line, lines, description, is_macro):
                        continue

                    issues.append(
                        Issue(
                            file=str(file_path),
                            line=line_num,
                            column=1,
                            code="STUB",
                            message=f"{description}: {line.strip()[:60]}",
                            severity=Severity.WARNING,
                            source="stub-check",
                            suggestion="Remove placeholder or implement functionality",
                        )
                    )

        return issues

    def _is_test_file(self, file_path: Path) -> bool:
        """Check if a file is a test file (exempt from stub detection)."""
        # Check filename for test patterns (test_foo.rs, foo_test.rs, tests.rs)
        return "test" in file_path.name.lower()

    def _is_legitimate_rust_pattern(
        self,
        file_path: Path,
        line_num: int,
        line: str,
        lines: list[str],
        description: str,
        is_macro: bool,
    ) -> bool:
        """Check if a stub pattern is actually legitimate in Rust.

        Exemptions:
        - unreachable!() in match arms (legitimate safety assertion)
        - unimplemented!() in trait default impls with doc comments
        """
        # unreachable!() in match arms is a legitimate safety assertion
        if "unreachable!() macro" in description.lower():
            # Check if we're inside a match block by looking for match/=> patterns
            for i in range(max(0, line_num - 10), line_num - 1):
                if "match " in lines[i] or "=>" in lines[i]:
                    return True

        # unimplemented!() in trait default impls with doc comments
        if "unimplemented!() macro" in description.lower():
            # Look for trait + fn context with doc comments
            has_doc = False
            has_trait_fn = False
            for i in range(max(0, line_num - 10), line_num - 1):
                stripped = lines[i].strip()
                if stripped.startswith("///") or stripped.startswith("//!"):
                    has_doc = True
                if "fn " in lines[i] and (
                    "trait " in "\n".join(lines[max(0, i - 10) : i + 1])
                    or "impl " not in "\n".join(lines[max(0, i - 5) : i + 1])
                ):
                    has_trait_fn = True
            if has_doc and has_trait_fn:
                return True

        return False


# Convenience functions for direct use
def check_files(
    paths: list[str | Path],
    config: CheckConfig | None = None,
    workspace_root: str | Path | None = None,
) -> CheckResult:
    """Check Rust files for issues.

    Args:
        paths: Files or directories to check
        config: Optional config (defaults loaded from Cargo.toml)

    Returns:
        CheckResult with issues found
    """
    checker = RustChecker(config, workspace_root=workspace_root)
    return checker.check_files(paths)


def check_content(content: str, filename: str = "stdin.rs", config: CheckConfig | None = None) -> CheckResult:
    """Check Rust content string.

    Args:
        content: Rust source code as string
        filename: Virtual filename for error reporting
        config: Optional config

    Returns:
        CheckResult with issues found
    """
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".rs", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        checker = RustChecker(config)
        result = checker.check_files([temp_path])
        # Rewrite paths to use the original filename
        for issue in result.issues:
            if issue.file == temp_path:
                issue.file = filename
        return result
    finally:
        Path(temp_path).unlink(missing_ok=True)
