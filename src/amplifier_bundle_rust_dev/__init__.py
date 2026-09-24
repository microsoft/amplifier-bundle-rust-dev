"""Amplifier Rust Development Bundle.

Provides comprehensive Rust development tools including:
- Code quality checks (cargo fmt, clippy, cargo check)
- Stub/placeholder detection
- Integration with Amplifier as tool and hook modules
"""

from .checker import RustChecker
from .checker import check_content
from .checker import check_files
from .models import CheckConfig
from .models import CheckResult
from .models import Issue
from .models import Severity

__version__ = "0.2.0"

__all__ = [
    "RustChecker",
    "check_files",
    "check_content",
    "CheckResult",
    "Issue",
    "Severity",
    "CheckConfig",
]
