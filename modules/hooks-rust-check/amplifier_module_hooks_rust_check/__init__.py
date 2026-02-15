"""Amplifier hook module for automatic Rust code checking.

This hook triggers on file write/edit events and runs Rust quality
checks, injecting feedback into the agent's context when issues are found.

Features:
- Severity-adaptive display (more detail for errors, less for warnings)
- Progress tracking across repeated edits to same file
- Clean pass indicator for checked files
- Relative path display for readability
- Configurable verbosity levels
"""

import fnmatch
from pathlib import Path
from typing import Any
from typing import Literal

from amplifier_core import HookResult

from amplifier_bundle_rust_dev import CheckConfig
from amplifier_bundle_rust_dev import check_files
from amplifier_bundle_rust_dev.models import CheckResult
from amplifier_bundle_rust_dev.models import Issue
from amplifier_bundle_rust_dev.models import Severity

# Icons for different states (work in monospace terminals)
ICONS = {
    "clean": "\u2713",  # checkmark
    "minor": "\u25d0",  # half circle (warnings/style)
    "errors": "\u25cf",  # filled circle (errors)
    "stubs": "\u25d1",  # half circle reversed (incomplete)
}


class FileCheckState:
    """Tracks check state for a single file across edits."""

    def __init__(self):
        self.error_count: int = 0
        self.warning_count: int = 0
        self.check_count: int = 0

    def update(self, errors: int, warnings: int) -> tuple[int, int]:
        """Update state and return previous counts for comparison."""
        prev_errors, prev_warnings = self.error_count, self.warning_count
        self.error_count = errors
        self.warning_count = warnings
        self.check_count += 1
        return prev_errors, prev_warnings

    @property
    def total_issues(self) -> int:
        return self.error_count + self.warning_count


class RustCheckHooks:
    """Hook handlers for automatic Rust quality checking."""

    def __init__(
        self, config: dict[str, Any] | None = None, working_dir: Path | None = None
    ):
        """Initialize hooks with configuration.

        Args:
            config: Hook configuration dict
            working_dir: Working directory for path resolution
        """
        config = config or {}
        self.enabled = config.get("enabled", True)
        self.working_dir = working_dir or Path.cwd()
        self.file_patterns = config.get("file_patterns", ["*.rs"])
        self.report_level = config.get("report_level", "warning")
        self.auto_inject = config.get("auto_inject", True)
        self.checks = config.get("checks", ["format", "lint", "types", "stubs"])
        self.verbosity: Literal["minimal", "normal", "detailed"] = config.get(
            "verbosity", "normal"
        )
        self.show_clean = config.get("show_clean", True)

        # Build check config
        self.check_config = CheckConfig(
            enable_cargo_fmt="format" in self.checks,
            enable_clippy="lint" in self.checks,
            enable_cargo_check="types" in self.checks,
            enable_stub_check="stubs" in self.checks,
        )

        # Track file state for progress tracking
        self._file_states: dict[str, FileCheckState] = {}

    def _matches_patterns(self, file_path: str) -> bool:
        """Check if file path matches any configured pattern."""
        path = Path(file_path)
        for pattern in self.file_patterns:
            if fnmatch.fnmatch(path.name, pattern):
                return True
            if fnmatch.fnmatch(str(path), pattern):
                return True
        return False

    def _filter_by_level(self, issues: list[Issue]) -> list[Issue]:
        """Filter issues by configured report level."""
        level_order = {"error": 0, "warning": 1, "info": 2}
        min_level = level_order.get(self.report_level, 1)
        return [i for i in issues if level_order.get(i.severity.value, 0) <= min_level]

    def _get_relative_path(self, file_path: str) -> str:
        """Convert absolute path to relative path for display."""
        try:
            path = Path(file_path)
            cwd = self.working_dir

            if path.is_absolute():
                try:
                    return str(path.relative_to(cwd))
                except ValueError:
                    pass
                try:
                    return f"~/{path.relative_to(Path.home())}"
                except ValueError:
                    pass

            return path.name
        except Exception:
            return Path(file_path).name

    def _get_file_state(self, file_path: str) -> FileCheckState:
        """Get or create file state tracker."""
        abs_path = str(Path(file_path).resolve())
        if abs_path not in self._file_states:
            self._file_states[abs_path] = FileCheckState()
        return self._file_states[abs_path]

    def _categorize_issues(self, issues: list[Issue]) -> dict[str, list[Issue]]:
        """Categorize issues by type for display."""
        categories: dict[str, list[Issue]] = {
            "compile_errors": [],
            "lint_warnings": [],
            "style_issues": [],
            "stubs": [],
        }
        for issue in issues:
            if issue.source == "cargo-check" and issue.severity == Severity.ERROR:
                categories["compile_errors"].append(issue)
            elif issue.source == "stub-check":
                categories["stubs"].append(issue)
            elif issue.source == "cargo-fmt":
                categories["style_issues"].append(issue)
            elif issue.severity == Severity.ERROR:
                categories["compile_errors"].append(issue)
            else:
                categories["lint_warnings"].append(issue)
        return categories

    def _format_category_summary(self, categories: dict[str, list[Issue]]) -> str:
        """Format issue categories into a readable summary."""
        parts = []
        compile_errors = len(categories["compile_errors"])
        lint_warnings = len(categories["lint_warnings"])
        style_issues = len(categories["style_issues"])
        stubs = len(categories["stubs"])

        if compile_errors:
            parts.append(
                f"{compile_errors} compile error{'s' if compile_errors != 1 else ''}"
            )
        if lint_warnings:
            parts.append(
                f"{lint_warnings} lint warning{'s' if lint_warnings != 1 else ''}"
            )
        if style_issues:
            parts.append(
                f"{style_issues} style issue{'s' if style_issues != 1 else ''}"
            )
        if stubs:
            parts.append(f"{stubs} stub{'s' if stubs != 1 else ''}")
        return ", ".join(parts) if parts else "no issues"

    def _get_severity_icon(
        self, result: CheckResult, categories: dict[str, list[Issue]]
    ) -> str:
        """Get appropriate icon based on severity."""
        if result.clean:
            return ICONS["clean"]
        if categories["stubs"] and not categories["compile_errors"]:
            return ICONS["stubs"]
        if result.error_count > 0:
            return ICONS["errors"]
        return ICONS["minor"]

    def _format_user_message(
        self,
        result: CheckResult,
        display_path: str,
        file_state: FileCheckState,
        prev_errors: int,
        prev_warnings: int,
    ) -> tuple[str, Literal["info", "warning", "error"]]:
        """Format the user-facing message based on verbosity and state."""
        categories = self._categorize_issues(result.issues)
        icon = self._get_severity_icon(result, categories)
        category_summary = self._format_category_summary(categories)

        if result.clean:
            level: Literal["info", "warning", "error"] = "info"
        elif result.error_count > 0:
            level = "error"
        else:
            level = "warning"

        if result.clean:
            if file_state.check_count > 1 and (prev_errors > 0 or prev_warnings > 0):
                return (
                    f"{icon} {display_path}: clean (was {prev_errors + prev_warnings} issues)",
                    "info",
                )
            else:
                return f"{icon} {display_path}: clean", "info"

        if self.verbosity == "minimal":
            total = len(result.issues)
            return (
                f"{icon} {display_path}: {total} issue{'s' if total != 1 else ''}",
                level,
            )

        message = f"{icon} {display_path}: {category_summary}"
        if file_state.check_count > 1:
            prev_total = prev_errors + prev_warnings
            curr_total = result.error_count + result.warning_count
            if curr_total < prev_total:
                message += f" (was {prev_total})"

        return message, level

    def _format_detailed_issues(self, result: CheckResult, max_issues: int = 5) -> str:
        """Format detailed issue lines for expanded display."""
        lines = []
        sorted_issues = sorted(
            result.issues,
            key=lambda i: (0 if i.severity == Severity.ERROR else 1, i.line),
        )
        for issue in sorted_issues[:max_issues]:
            severity_label = "error" if issue.severity == Severity.ERROR else "warn "
            msg = (
                issue.message[:60] + "..." if len(issue.message) > 63 else issue.message
            )
            lines.append(f"\u2502 {severity_label}  line {issue.line:<4}  {msg}")
        if len(result.issues) > max_issues:
            lines.append(f"\u2502 ... and {len(result.issues) - max_issues} more")
        return "\n".join(lines)

    def _should_show_details(self, result: CheckResult) -> bool:
        """Determine if we should show detailed issue list."""
        if self.verbosity == "detailed":
            return True
        if self.verbosity == "minimal":
            return False
        return result.error_count > 0

    async def handle_tool_post(self, event: str, data: dict[str, Any]) -> HookResult:
        """Handle post-tool-use events to check Rust files.

        Triggers on: write_file, edit_file, Write, Edit, MultiEdit
        """
        if not self.enabled:
            return HookResult(action="continue")

        tool_name = data.get("tool_name", "")
        write_tools = ["write_file", "edit_file", "Write", "Edit", "MultiEdit"]

        if tool_name not in write_tools:
            return HookResult(action="continue")

        tool_input = data.get("tool_input", {})
        file_path = tool_input.get("file_path", tool_input.get("path", ""))

        if not file_path:
            return HookResult(action="continue")

        if not self._matches_patterns(file_path):
            return HookResult(action="continue")

        if not Path(file_path).exists():
            return HookResult(action="continue")

        result = check_files([file_path], config=self.check_config)
        result.issues = self._filter_by_level(result.issues)

        display_path = self._get_relative_path(file_path)
        file_state = self._get_file_state(file_path)
        prev_errors, prev_warnings = file_state.update(
            result.error_count, result.warning_count
        )

        if result.clean:
            if self.show_clean:
                message, level = self._format_user_message(
                    result, display_path, file_state, prev_errors, prev_warnings
                )
                return HookResult(
                    action="continue",
                    user_message=message,
                    user_message_level=level,
                )
            return HookResult(action="continue")

        if (
            file_state.check_count > 1
            and result.error_count == prev_errors
            and result.warning_count == prev_warnings
            and self.verbosity != "detailed"
        ):
            return HookResult(action="continue")

        user_message, user_level = self._format_user_message(
            result, display_path, file_state, prev_errors, prev_warnings
        )

        if self._should_show_details(result):
            details = self._format_detailed_issues(result)
            user_message = f"{user_message}\n{details}"

        if self.auto_inject:
            context_lines = [f"Rust check found issues in {display_path}:"]
            for issue in result.issues[:10]:
                context_lines.append(f"- {issue.format_short()}")
            if len(result.issues) > 10:
                context_lines.append(f"  ... and {len(result.issues) - 10} more issues")

            context_text = "\n".join(context_lines)

            return HookResult(
                action="inject_context",
                context_injection=context_text,
                context_injection_role="user",
                ephemeral=True,
                append_to_last_tool_result=True,
                user_message=user_message,
                user_message_level=user_level,
                user_message_source="rust-check",
            )
        else:
            return HookResult(
                action="continue",
                user_message=user_message,
                user_message_level=user_level,
            )


async def mount(
    coordinator: Any, config: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Mount the Rust check hooks into the coordinator.

    Args:
        coordinator: The Amplifier coordinator instance
        config: Module configuration for the hooks

    Returns:
        Module metadata
    """
    working_dir_str = coordinator.get_capability("session.working_dir")
    working_dir = Path(working_dir_str) if working_dir_str else None

    hooks = RustCheckHooks(config, working_dir=working_dir)

    coordinator.hooks.register(
        "tool:post",
        hooks.handle_tool_post,
        priority=15,
        name="rust-check",
    )

    return {
        "name": "hooks-rust-check",
        "version": "0.1.0",
        "provides": ["rust_check_hook"],
        "config": {
            "enabled": hooks.enabled,
            "file_patterns": hooks.file_patterns,
            "report_level": hooks.report_level,
            "auto_inject": hooks.auto_inject,
            "checks": hooks.checks,
            "verbosity": hooks.verbosity,
            "show_clean": hooks.show_clean,
        },
    }
