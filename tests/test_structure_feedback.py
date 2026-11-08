"""Edited-file feedback remains advisory, bounded and current."""

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch
from xml.etree import ElementTree

import pytest

from amplifier_bundle_rust_dev.models import CheckResult
from amplifier_bundle_rust_dev.models import Issue
from amplifier_bundle_rust_dev.models import Severity


@pytest.fixture
def hooks(tmp_path, monkeypatch):
    monkeypatch.delenv("AMPLIFIER_RUST_ALLOW_WORKSPACE_EXECUTION", raising=False)
    monkeypatch.setitem(sys.modules, "amplifier_core", SimpleNamespace(HookResult=SimpleNamespace))
    path = Path(__file__).parents[1] / "modules/hooks-rust-check/amplifier_module_hooks_rust_check/__init__.py"
    spec = importlib.util.spec_from_file_location("rust_structure_hooks", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        "amplifier_bundle_rust_dev.checker.subprocess.run", Mock(side_effect=AssertionError("Cargo ran"))
    )
    return module


def event(path, **extra):
    return {"tool_name": "write_file", "tool_input": {"file_path": str(path)}, "result": {"success": True}, **extra}


def invoke(hook, data):
    return asyncio.run(hook.handle_tool_post("tool:post", data))


def test_default_hook_reports_size_without_cargo_and_new_counts_arrive(hooks, tmp_path):
    path = tmp_path / "main.rs"
    hook = hooks.RustCheckHooks(working_dir=tmp_path)
    path.write_text("// source\n" * 501)
    first = invoke(hook, event(path))
    assert first.action == "inject_context" and "501 physical lines" in first.context_injection
    assert first.user_message_level == "warning"
    assert invoke(hook, event(path)).action == "continue"
    path.write_text("// source\n" * 502)
    assert "502 physical lines" in invoke(hook, event(path)).context_injection
    path.write_text("// source\n")
    assert invoke(hook, event(path)).action == "continue"
    path.write_text("// source\n" * 502)
    assert invoke(hook, event(path)).action == "inject_context"


@pytest.mark.parametrize("result", [{"success": False}, SimpleNamespace(success=False)])
@pytest.mark.parametrize("field", ["result", "tool_result"])
def test_failed_write_does_not_read_or_emit_feedback(hooks, tmp_path, result, field):
    hook = hooks.RustCheckHooks(working_dir=tmp_path)
    data = {"tool_name": "edit_file", "tool_input": {"path": "main.rs"}, field: result}
    with patch.object(hooks, "check_files", side_effect=AssertionError("failed write checked")):
        assert invoke(hook, data).action == "continue"
    assert not hook._file_states


def test_file_scope_does_not_become_directory_scan_or_patch_parser(hooks, tmp_path):
    path = tmp_path / "directory.rs"
    path.mkdir()
    hook = hooks.RustCheckHooks(working_dir=tmp_path)
    with patch.object(hooks, "check_files", side_effect=AssertionError("unexpected analysis")):
        assert invoke(hook, event(path)).action == "continue"
        assert invoke(hook, event(path, tool_name="apply_patch")).action == "continue"


def test_hook_configuration_can_disable_or_tune_structure(hooks, tmp_path):
    path = tmp_path / "main.rs"
    path.write_text("// source\n" * 501)
    (tmp_path / "Cargo.toml").write_text("[package.metadata.amplifier-rust-dev]\nenable_structure_check=false\n")
    assert invoke(hooks.RustCheckHooks(working_dir=tmp_path), event(path)).action == "continue"
    hook = hooks.RustCheckHooks(
        {"checks": ["structure"], "check_options": {"enable_structure_check": True, "max_file_lines": 600}},
        working_dir=tmp_path,
    )
    assert hook.check_config.structure_enabled and not hook.check_config.enable_stub_check
    assert invoke(hook, event(path)).action == "continue"
    disabled = hooks.RustCheckHooks({"enabled": False}, working_dir=tmp_path)
    with patch.object(hooks, "check_files", side_effect=AssertionError("disabled hook checked")):
        assert invoke(disabled, event(path)).action == "continue"


def test_excluded_and_oversized_sources_never_claim_clean(hooks, tmp_path):
    path = tmp_path / "main.rs"
    hook = hooks.RustCheckHooks({"check_options": {"structure_max_bytes": 80}}, working_dir=tmp_path)
    path.write_text("// @generated\ntodo!();\n")
    excluded = invoke(hook, event(path))
    assert excluded.action == "continue" and not getattr(excluded, "user_message", None)
    path.write_text("todo!();\n" * 100)
    skipped = invoke(hook, event(path))
    assert "STRUCTURE-SKIPPED" in skipped.context_injection and "STUB]" not in skipped.context_injection


def test_file_state_cache_is_bounded_and_uses_session_paths(hooks, tmp_path, monkeypatch):
    hook = hooks.RustCheckHooks({"max_cached_files": 2, "check_options": {"max_file_lines": 1}}, working_dir=tmp_path)
    monkeypatch.chdir(tmp_path.parent)
    for name in ("first", "second", "first", "third"):
        (tmp_path / f"{name}.rs").write_text("// source\n" * 2)
        invoke(hook, event(f"{name}.rs"))
    assert list(hook._file_states) == [str(tmp_path / "first.rs"), str(tmp_path / "third.rs")]
    assert invoke(hook, event("second.rs")).action == "inject_context"
    (tmp_path / "second.rs").unlink()
    assert invoke(hook, event("second.rs")).action == "continue"
    assert str(tmp_path / "second.rs") not in hook._file_states


def test_changed_diagnostic_content_with_same_count_is_delivered(hooks, tmp_path):
    path = tmp_path / "main.rs"
    path.touch()
    hook = hooks.RustCheckHooks(working_dir=tmp_path)
    for text in ("First issue", "Second issue"):
        issue = Issue(str(path), 1, 1, "CODE", text, Severity.WARNING, "clippy")
        with patch.object(hooks, "check_files", return_value=CheckResult(issues=[issue])):
            assert text in invoke(hook, event(path)).context_injection


def test_escaped_feedback_respects_budget_without_broken_wrapper(hooks, tmp_path):
    path = tmp_path / "main.rs"
    path.touch()
    hook = hooks.RustCheckHooks({"max_context_chars": 512, "verbosity": "detailed"}, working_dir=tmp_path)
    issue = Issue(str(path), 1, 1, "CODE", '<&"' * 10000, Severity.ERROR, "clippy")
    with patch.object(hooks, "check_files", return_value=CheckResult(issues=[issue] * 50)):
        result = invoke(hook, event(path))
    assert len(result.context_injection) <= 512 and len(result.user_message) <= 1000
    assert result.context_injection_role == "user" and result.ephemeral
    assert result.append_to_last_tool_result
    ElementTree.fromstring(result.context_injection)


def test_auto_inject_optout_still_reports_user_advisory(hooks, tmp_path):
    path = tmp_path / "main.rs"
    path.write_text("// source\n" * 501)
    result = invoke(hooks.RustCheckHooks({"auto_inject": False}, working_dir=tmp_path), event(path))
    assert result.action == "continue" and result.user_message_level == "warning"
    assert not getattr(result, "context_injection", None)


@pytest.mark.parametrize(
    "option,value",
    [("max_cached_files", 0), ("max_cached_files", True), ("max_context_chars", 511), ("max_context_chars", "4096")],
)
def test_hook_budgets_reject_invalid_configuration(hooks, option, value):
    with pytest.raises(ValueError, match=option):
        hooks.RustCheckHooks({option: value})
