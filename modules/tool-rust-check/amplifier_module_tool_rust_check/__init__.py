"""Amplifier tool module for Rust code quality checks.

This module provides the `rust_check` tool that agents can use to
check Rust code for formatting, linting, type/compile errors, and stubs.
"""

from pathlib import Path
from typing import Any

from amplifier_core import ToolResult

from amplifier_bundle_rust_dev import check_files
from amplifier_bundle_rust_dev.config import find_cargo_toml
from amplifier_bundle_rust_dev.config import load_config
from amplifier_bundle_rust_dev.config import workspace_execution_enabled_by_host


class RustCheckTool:
    """Tool for checking Rust code quality."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        working_dir: Path | None = None,
    ):
        # Bundle configuration is mergeable with project-owned content. Only the
        # host process environment may grant permission to execute a workspace.
        self.allow_workspace_execution = workspace_execution_enabled_by_host()
        self.working_dir = working_dir or Path.cwd()

    @property
    def name(self) -> str:
        return "rust_check"

    @property
    def description(self) -> str:
        return """Check Rust code for quality issues.

Runs cargo fmt (formatting), clippy (linting), cargo check (type/compile errors),
and stub detection on Rust files or projects. Cargo-based checks are skipped
    unless the host process explicitly opts into a trusted workspace with
    AMPLIFIER_RUST_ALLOW_WORKSPACE_EXECUTION=true.

Input options:
- paths: List of file paths or directories to check
- checks: Specific checks to run (default: all)

Examples:
- Check current project: {"paths": ["."]}
- Check a directory: {"paths": ["src/"]}
- Check a specific file: {"paths": ["src/main.rs"]}
- Run only clippy: {"checks": ["lint"]}
- Run format + lint: {"checks": ["format", "lint"]}

Returns:
- success: True if no errors (warnings are OK)
- clean: True if no issues at all
- summary: Human-readable summary
- issues: List of issues with file, line, code, message, severity"""

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of file paths or directories to check",
                },
                "checks": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["format", "lint", "types", "stubs"],
                    },
                    "description": "Specific checks to run (default: all). 'types' runs cargo check.",
                },
            },
        }

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        """Execute the Rust check tool.

        Args:
            input_data: Tool input with paths and/or checks

        Returns:
            ToolResult with check output
        """
        paths = input_data.get("paths")
        checks = input_data.get("checks")

        # Build config based on requested checks
        config_overrides = {}
        config_overrides["allow_workspace_execution"] = self.allow_workspace_execution
        if checks:
            config_overrides["enable_cargo_fmt"] = "format" in checks
            config_overrides["enable_clippy"] = "lint" in checks
            config_overrides["enable_cargo_check"] = "types" in checks
            config_overrides["enable_stub_check"] = "stubs" in checks

        cargo_toml = find_cargo_toml(self.working_dir) or self.working_dir / "Cargo.toml"
        config = load_config(config_path=cargo_toml, overrides=config_overrides)

        # Run checks
        if paths:
            result = check_files(paths, config=config, workspace_root=self.working_dir)
        else:
            result = check_files(["."], config=config, workspace_root=self.working_dir)

        return ToolResult(success=result.success, output=result.to_tool_output())


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Mount the rust_check tool into the coordinator.

    Args:
        coordinator: The Amplifier coordinator instance
        config: Optional module configuration

    Returns:
        Module metadata
    """
    working_dir_str = coordinator.get_capability("session.working_dir")
    working_dir = Path(working_dir_str) if working_dir_str else None
    tool = RustCheckTool(config, working_dir=working_dir)

    # Register the tool
    await coordinator.mount("tools", tool, name=tool.name)

    return {
        "name": "tool-rust-check",
        "version": "0.1.0",
        "provides": ["rust_check"],
    }
