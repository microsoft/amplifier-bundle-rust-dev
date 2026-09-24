"""Configuration loading for Rust checks."""

import os
from pathlib import Path

from .models import CheckConfig

# tomllib is in stdlib from Python 3.11+
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]


def find_cargo_toml(start_path: Path | None = None) -> Path | None:
    """Find Cargo.toml by walking up from start_path."""
    current = start_path or Path.cwd()

    while current != current.parent:
        candidate = current / "Cargo.toml"
        if candidate.exists():
            return candidate
        current = current.parent

    return None


def load_config(
    config_path: Path | None = None,
    overrides: dict | None = None,
) -> CheckConfig:
    """Load configuration from Cargo.toml with optional overrides.

    Config is loaded from (in order of priority):
    1. Explicit overrides dict
    2. Environment variables (AMPLIFIER_RUST_*)
    3. Cargo.toml [workspace.metadata.amplifier-rust-dev] or
       [package.metadata.amplifier-rust-dev] section
    4. Default values

    Args:
        config_path: Explicit path to Cargo.toml (auto-discovered if None)
        overrides: Dict of config values to override

    Returns:
        Merged CheckConfig
    """
    config_data: dict = {}

    # Load from Cargo.toml
    if tomllib:
        toml_path = config_path or find_cargo_toml()
        if toml_path and toml_path.exists():
            try:
                with open(toml_path, "rb") as f:
                    cargo_toml = tomllib.load(f)

                # Try workspace metadata first, then package metadata
                config_data = cargo_toml.get("workspace", {}).get("metadata", {}).get("amplifier-rust-dev", {})
                if not config_data:
                    config_data = cargo_toml.get("package", {}).get("metadata", {}).get("amplifier-rust-dev", {})
                # Workspace content is untrusted input and cannot grant itself
                # permission to execute Cargo, build scripts, or proc macros.
                config_data.pop("allow_workspace_execution", None)
            except Exception:
                pass  # Graceful fallback to defaults

    # Apply environment variables
    env_mapping = {
        "AMPLIFIER_RUST_ENABLE_CARGO_FMT": "enable_cargo_fmt",
        "AMPLIFIER_RUST_ENABLE_CLIPPY": "enable_clippy",
        "AMPLIFIER_RUST_ENABLE_CARGO_CHECK": "enable_cargo_check",
        "AMPLIFIER_RUST_ENABLE_STUB_CHECK": "enable_stub_check",
        "AMPLIFIER_RUST_FAIL_ON_WARNING": "fail_on_warning",
        "AMPLIFIER_RUST_ALLOW_WORKSPACE_EXECUTION": "allow_workspace_execution",
    }

    for env_var, config_key in env_mapping.items():
        value = os.environ.get(env_var)
        if value is not None:
            if value.lower() in ("true", "1", "yes"):
                config_data[config_key] = True
            elif value.lower() in ("false", "0", "no"):
                config_data[config_key] = False

    # Apply explicit overrides
    if overrides:
        config_data.update(overrides)

    return CheckConfig.from_dict(config_data)
