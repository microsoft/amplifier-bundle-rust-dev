"""Command failures must not become a successful, empty diagnostic result."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from amplifier_bundle_rust_dev.checker import RustChecker
from amplifier_bundle_rust_dev.models import CheckConfig


@pytest.fixture
def run_check(tmp_path):
    source = tmp_path / "src/lib.rs"
    source.parent.mkdir()
    source.write_text("pub fn value() -> u32 { 1 }\n")
    (tmp_path / "Cargo.toml").write_text('[package]\nname="sample"\nversion="0.1.0"\n')

    def run(check, returncode=0, stdout="", stderr="", error=None):
        config = CheckConfig(
            allow_workspace_execution=True,
            enable_cargo_fmt=check == "format",
            enable_clippy=check == "lint",
            enable_cargo_check=check == "types",
            enable_stub_check=False,
        )
        process = subprocess.CompletedProcess(["cargo"], returncode, stdout, stderr)
        with patch("amplifier_bundle_rust_dev.checker.subprocess.run", return_value=process, side_effect=error):
            return RustChecker(config, workspace_root=tmp_path).check_files([source])

    return run


@pytest.mark.parametrize("check", ["format", "lint", "types"])
@pytest.mark.parametrize("returncode", [1, 101, -9])
def test_failed_command_without_compiler_diagnostics_is_not_clean(run_check, check, returncode):
    result = run_check(check, returncode, stderr="Cargo configuration failed\n" * 100)
    assert not result.success and not result.clean
    assert result.issues[0].code == "CHECK-FAILED"
    assert f"exit {returncode}" in result.issues[0].message
    assert "Cargo configuration failed" in result.issues[0].message
    assert len(result.issues[0].message) < 650
    assert result.to_tool_output()["success"] is False


@pytest.mark.parametrize("check", ["format", "lint", "types"])
def test_successful_empty_check_with_progress_on_stderr_stays_clean(run_check, check):
    result = run_check(check, stderr="Checking sample\nFinished dev profile\n")
    assert result.success and result.clean


@pytest.mark.parametrize("heading", ["Diff in src/main.rs at line 5:", "Diff in src/main.rs:5:"])
def test_rustfmt_formatting_difference_stays_an_advisory_warning(run_check, heading):
    result = run_check("format", 1, stdout=heading + "\n-fn main(){}\n+fn main() {}\n")
    assert result.success and not result.clean
    assert result.warning_count == 1 and result.error_count == 0
    assert (result.issues[0].file, result.issues[0].line, result.issues[0].code) == ("src/main.rs", 5, "FORMAT")


@pytest.mark.parametrize(
    "stderr,failed",
    [
        ("error: this file contains an unclosed delimiter", True),
        ("Warning: can't set unstable formatting option on stable", False),
    ],
)
def test_formatting_diffs_do_not_hide_another_targets_parse_error(run_check, stderr, failed):
    result = run_check("format", 1, stdout="Diff in src/lib.rs:1:\n-fn f(){}\n+fn f() {}\n", stderr=stderr)
    assert result.warning_count == 1
    assert result.success is not failed
    assert result.error_count == int(failed)
    if failed:
        assert result.issues[-1].code == "CHECK-FAILED"
        assert "unclosed delimiter" in result.issues[-1].message


@pytest.mark.parametrize("returncode", [0, 1])
def test_unrecognized_fmt_output_is_not_a_clean_format_check(run_check, returncode):
    result = run_check("format", returncode, stdout="unrecognized formatter output")
    assert not result.success and result.issues[0].code == "CHECK-FAILED"


@pytest.mark.parametrize("check", ["lint", "types"])
def test_valid_compiler_errors_are_preserved_without_duplicate_failure(run_check, check):
    output = (Path(__file__).parent / "fixtures/cargo_check_errors.json").read_text()
    result = run_check(check, 101, output, "error: could not compile sample")
    assert not result.success and result.error_count == 1 and result.warning_count == 1
    assert [issue.code for issue in result.issues] == ["E0308", "unused_imports"]


@pytest.mark.parametrize("check", ["lint", "types"])
@pytest.mark.parametrize("returncode", [0, 101])
def test_warnings_are_retained_but_do_not_hide_command_failure(run_check, check, returncode):
    output = (Path(__file__).parent / "fixtures/cargo_clippy_warnings.json").read_text()
    result = run_check(check, returncode, output, "compiler progress")
    assert result.warning_count == 2
    assert result.success is (returncode == 0)
    assert result.error_count == int(returncode != 0)


@pytest.mark.parametrize("check", ["lint", "types"])
@pytest.mark.parametrize(
    "output",
    [
        '{"reason":"compiler-message",truncated',
        '{"reason":"build-finished",truncated',
        '{"reason":"compiler-message","message":null}',
        '{"reason":"compiler-message","message":{"level":"error","message":5}}',
        '{"reason":"compiler-message","message":{"level":"warning","message":"w","spans":[null]}}',
        '{"reason":"build-finished","success":"yes"}',
    ],
)
def test_malformed_json_diagnostics_report_failure_without_crashing(run_check, check, output):
    result = run_check(check, stdout=output)
    assert not result.success and not result.clean
    assert result.issues[0].code == "CHECK-FAILED"
    assert "malformed" in result.issues[0].message


@pytest.mark.parametrize("check", ["lint", "types"])
def test_non_json_macro_output_and_other_cargo_records_are_not_errors(run_check, check):
    output = 'procedural macro status\n{"macro":"status"}\n{not json: macro status\n' + "\n".join(
        json.dumps(row)
        for row in [
            {"reason": "compiler-artifact"},
            {"reason": "build-script-executed"},
            {"reason": "future-cargo-record"},
            {"reason": "build-finished", "success": True},
        ]
    )
    result = run_check(check, stdout=output, stderr="Checking sample")
    assert result.success and result.clean


@pytest.mark.parametrize("check", ["lint", "types"])
def test_unsuccessful_build_record_without_diagnostic_is_not_clean(run_check, check):
    result = run_check(check, stdout='{"reason":"build-finished","success":false}')
    assert not result.success and "unsuccessful build" in result.issues[0].message


@pytest.mark.parametrize("check", ["format", "lint", "types"])
@pytest.mark.parametrize("error", [PermissionError("cannot execute cargo"), UnicodeError("invalid tool text")])
def test_execution_and_output_decode_errors_report_failed_check(run_check, check, error):
    result = run_check(check, error=error)
    assert not result.success and result.issues[0].code == "CHECK-FAILED"
