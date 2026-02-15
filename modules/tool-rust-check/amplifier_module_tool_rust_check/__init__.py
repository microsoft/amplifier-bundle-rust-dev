"""Amplifier tool module for Rust code quality checks.

This module provides the `rust_check` tool that agents can use to
check Rust code for formatting, linting, type/compile errors, and stubs.
"""

from typing import Any

from amplifier_core import ToolResult
from amplifier_bundle_rust_dev import CheckConfig, check_files


class RustCheckTool:
    """Tool for checking Rust code quality."""

    @property
    def name(self) -> str:
        return "rust_check"

    @property
    def description(self) -> str:
        return """Check Rust code for quality issues.

Runs cargo fmt (formatting), clippy (linting), cargo check (type/compile errors),
and stub detection on Rust files or projects.

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
        if checks:
            config_overrides["enable_cargo_fmt"] = "format" in checks
            config_overrides["enable_clippy"] = "lint" in checks
            config_overrides["enable_cargo_check"] = "types" in checks
            config_overrides["enable_stub_check"] = "stubs" in checks

        config = CheckConfig.from_dict(config_overrides) if config_overrides else None

        # Run checks
        if paths:
            result = check_files(paths, config=config)
        else:
            result = check_files(["."], config=config)

        return ToolResult(success=result.success, output=result.to_tool_output())


async def mount(
    coordinator: Any, config: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Mount the rust_check tool into the coordinator.

    Args:
        coordinator: The Amplifier coordinator instance
        config: Optional module configuration

    Returns:
        Module metadata
    """
    tool = RustCheckTool()

    # Register the tool
    await coordinator.mount("tools", tool, name=tool.name)

    return {
        "name": "tool-rust-check",
        "version": "0.1.0",
        "provides": ["rust_check"],
    }
