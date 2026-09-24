"""Tests for RustChecker parsing logic."""

from pathlib import Path
from unittest.mock import patch

# These imports will fail until the checker is implemented — that's expected
from amplifier_bundle_rust_dev.checker import RustChecker
from amplifier_bundle_rust_dev.config import load_config
from amplifier_bundle_rust_dev.models import CheckConfig
from amplifier_bundle_rust_dev.models import Severity

FIXTURES = Path(__file__).parent / "fixtures"


class TestParseCargoFmtOutput:
    """Test cargo fmt --check output parsing."""

    def test_parses_files_needing_format(self):
        output = (FIXTURES / "cargo_fmt_needs_format.txt").read_text()
        checker = RustChecker(CheckConfig())
        result = checker._parse_cargo_fmt_output(output)

        assert len(result.issues) == 2
        assert result.checks_run == ["cargo-fmt"]

    def test_first_file_is_main_rs(self):
        output = (FIXTURES / "cargo_fmt_needs_format.txt").read_text()
        checker = RustChecker(CheckConfig())
        result = checker._parse_cargo_fmt_output(output)

        assert "src/main.rs" in result.issues[0].file
        assert result.issues[0].code == "FORMAT"
        assert result.issues[0].severity == Severity.WARNING
        assert result.issues[0].source == "cargo-fmt"

    def test_second_file_is_lib_rs(self):
        output = (FIXTURES / "cargo_fmt_needs_format.txt").read_text()
        checker = RustChecker(CheckConfig())
        result = checker._parse_cargo_fmt_output(output)

        assert "src/lib.rs" in result.issues[1].file

    def test_empty_output_means_clean(self):
        checker = RustChecker(CheckConfig())
        result = checker._parse_cargo_fmt_output("")

        assert result.clean
        assert result.checks_run == ["cargo-fmt"]

    def test_suggestion_mentions_cargo_fmt(self):
        output = (FIXTURES / "cargo_fmt_needs_format.txt").read_text()
        checker = RustChecker(CheckConfig())
        result = checker._parse_cargo_fmt_output(output)

        assert result.issues[0].suggestion is not None
        assert "cargo fmt" in result.issues[0].suggestion.lower()


class TestWorkspaceTrust:
    """Execution-capable checks require host trust and a validated workspace."""

    def test_untrusted_workspace_never_runs_subprocess(self, tmp_path):
        source = tmp_path / "src" / "lib.rs"
        source.parent.mkdir()
        source.write_text("pub fn value() -> u8 { 1 }\n")
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "sample"\nversion = "0.1.0"\n')
        config = CheckConfig(
            allow_workspace_execution=False,
            enable_cargo_fmt=True,
            enable_clippy=True,
            enable_cargo_check=True,
            enable_stub_check=False,
        )

        with patch("amplifier_bundle_rust_dev.checker.subprocess.run") as run:
            result = RustChecker(config, workspace_root=tmp_path).check_files([source])

        run.assert_not_called()
        assert result.issues[0].code == "WORKSPACE-UNTRUSTED"
        assert result.checks_run == ["cargo-skipped-untrusted"]

    def test_trusted_workspace_sets_canonical_cwd(self, tmp_path):
        source = tmp_path / "src" / "lib.rs"
        source.parent.mkdir()
        source.write_text("pub fn value() -> u8 { 1 }\n")
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "sample"\nversion = "0.1.0"\n')
        config = CheckConfig(
            allow_workspace_execution=True,
            enable_cargo_fmt=False,
            enable_clippy=False,
            enable_cargo_check=True,
            enable_stub_check=False,
        )

        with patch("amplifier_bundle_rust_dev.checker.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = ""
            RustChecker(config, workspace_root=tmp_path).check_files([source])

        run.assert_called_once_with(
            ["cargo", "check", "--message-format=json"],
            capture_output=True,
            text=True,
            cwd=tmp_path.resolve(),
            check=False,
        )

    def test_trusted_workspace_rejects_path_escape(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "Cargo.toml").write_text('[package]\nname = "sample"\nversion = "0.1.0"\n')
        outside = tmp_path / "outside.rs"
        outside.write_text("fn main() {}\n")
        config = CheckConfig(
            allow_workspace_execution=True,
            enable_cargo_fmt=False,
            enable_clippy=False,
            enable_cargo_check=True,
            enable_stub_check=False,
        )

        with patch("amplifier_bundle_rust_dev.checker.subprocess.run") as run:
            result = RustChecker(config, workspace_root=workspace).check_files([outside])

        run.assert_not_called()
        assert result.issues[0].code == "PATH-OUTSIDE-WORKSPACE"

    def test_cargo_metadata_cannot_grant_execution_trust(self, tmp_path):
        cargo_toml = tmp_path / "Cargo.toml"
        cargo_toml.write_text(
            "[package]\n"
            'name = "sample"\n'
            'version = "0.1.0"\n'
            "\n"
            "[package.metadata.amplifier-rust-dev]\n"
            "allow_workspace_execution = true\n"
        )

        config = load_config(config_path=cargo_toml)

        assert config.allow_workspace_execution is False


class TestParseClippyOutput:
    """Test cargo clippy --message-format=json output parsing."""

    def test_parses_warnings(self):
        output = (FIXTURES / "cargo_clippy_warnings.json").read_text()
        checker = RustChecker(CheckConfig())
        result = checker._parse_cargo_json_output(output, source="clippy")

        # Should find 2 warnings, skip the compiler-artifact and build-finished lines
        assert len(result.issues) == 2
        assert result.checks_run == ["clippy"]

    def test_first_warning_is_needless_return(self):
        output = (FIXTURES / "cargo_clippy_warnings.json").read_text()
        checker = RustChecker(CheckConfig())
        result = checker._parse_cargo_json_output(output, source="clippy")

        issue = result.issues[0]
        assert issue.code == "clippy::needless_return"
        assert issue.severity == Severity.WARNING
        assert issue.file == "src/lib.rs"
        assert issue.line == 5
        assert issue.column == 5
        assert issue.source == "clippy"

    def test_second_warning_is_unused_variable(self):
        output = (FIXTURES / "cargo_clippy_warnings.json").read_text()
        checker = RustChecker(CheckConfig())
        result = checker._parse_cargo_json_output(output, source="clippy")

        issue = result.issues[1]
        assert issue.code == "unused_variables"
        assert issue.file == "src/main.rs"
        assert issue.line == 3


class TestParseCargoCheckOutput:
    """Test cargo check --message-format=json output parsing."""

    def test_parses_error_and_warning(self):
        output = (FIXTURES / "cargo_check_errors.json").read_text()
        checker = RustChecker(CheckConfig())
        result = checker._parse_cargo_json_output(output, source="cargo-check")

        assert len(result.issues) == 2
        assert result.checks_run == ["cargo-check"]

    def test_type_error_is_error_severity(self):
        output = (FIXTURES / "cargo_check_errors.json").read_text()
        checker = RustChecker(CheckConfig())
        result = checker._parse_cargo_json_output(output, source="cargo-check")

        error = [i for i in result.issues if i.severity == Severity.ERROR][0]
        assert error.code == "E0308"
        assert error.message == "mismatched types"
        assert error.file == "src/main.rs"
        assert error.line == 10
        assert error.source == "cargo-check"

    def test_unused_import_is_warning(self):
        output = (FIXTURES / "cargo_check_errors.json").read_text()
        checker = RustChecker(CheckConfig())
        result = checker._parse_cargo_json_output(output, source="cargo-check")

        warning = [i for i in result.issues if i.severity == Severity.WARNING][0]
        assert warning.code == "unused_imports"

    def test_empty_output_means_clean(self):
        checker = RustChecker(CheckConfig())
        result = checker._parse_cargo_json_output("", source="cargo-check")

        assert result.clean


class TestStubDetection:
    """Test stub pattern detection in .rs files."""

    def test_finds_todo_macro(self):
        fixture = FIXTURES / "stub_sample.rs"
        checker = RustChecker(CheckConfig())
        issues = checker._check_file_for_stubs(fixture)

        todo_issues = [i for i in issues if "todo!() macro" in i.message.lower()]
        assert len(todo_issues) == 1

    def test_finds_todo_comment(self):
        fixture = FIXTURES / "stub_sample.rs"
        checker = RustChecker(CheckConfig())
        issues = checker._check_file_for_stubs(fixture)

        todo_comments = [i for i in issues if "TODO comment" in i.message]
        assert len(todo_comments) == 1

    def test_finds_fixme_comment(self):
        fixture = FIXTURES / "stub_sample.rs"
        checker = RustChecker(CheckConfig())
        issues = checker._check_file_for_stubs(fixture)

        fixme = [i for i in issues if "FIXME" in i.message]
        assert len(fixme) == 1

    def test_finds_hack_comment(self):
        fixture = FIXTURES / "stub_sample.rs"
        checker = RustChecker(CheckConfig())
        issues = checker._check_file_for_stubs(fixture)

        hack = [i for i in issues if "HACK" in i.message]
        assert len(hack) == 1

    def test_finds_unimplemented_not_in_trait(self):
        """unimplemented!() outside trait default impls should be flagged."""
        fixture = FIXTURES / "stub_sample.rs"
        checker = RustChecker(CheckConfig())
        issues = checker._check_file_for_stubs(fixture)

        # The unimplemented!() in temp_solution() should be flagged
        unimpl = [i for i in issues if "unimplemented!() macro" in i.message.lower() and i.source == "stub-check"]
        assert any(i.line == 17 for i in unimpl), "temp_solution's unimplemented!() should be flagged"

    def test_exempts_unreachable_in_match(self):
        """unreachable!() in match arms is a legitimate safety assertion."""
        fixture = FIXTURES / "stub_sample.rs"
        checker = RustChecker(CheckConfig())
        issues = checker._check_file_for_stubs(fixture)

        # The unreachable!() on line 33 is inside a match arm — should be exempt
        unreachable = [i for i in issues if "unreachable!() macro" in i.message.lower()]
        assert len(unreachable) == 0, "unreachable!() in match arms should be exempt"

    def test_exempts_unimplemented_in_trait_default_with_doc(self):
        """unimplemented!() in trait default impl with doc comment is exempt."""
        fixture = FIXTURES / "stub_sample.rs"
        checker = RustChecker(CheckConfig())
        issues = checker._check_file_for_stubs(fixture)

        # The unimplemented!() on line 25 is in a trait default impl with doc comments
        flagged_lines = [i.line for i in issues if "unimplemented!() macro" in i.message.lower()]
        assert 25 not in flagged_lines, "Trait default impl with doc should be exempt"

    def test_all_issues_are_stub_source(self):
        fixture = FIXTURES / "stub_sample.rs"
        checker = RustChecker(CheckConfig())
        issues = checker._check_file_for_stubs(fixture)

        for issue in issues:
            assert issue.source == "stub-check"
            assert issue.severity == Severity.WARNING
            assert issue.code == "STUB"


class TestStubExemptionInTestFiles:
    """Test that stubs in test files are exempt."""

    def test_todo_in_test_file_exempt(self, tmp_path):
        test_file = tmp_path / "tests" / "test_foo.rs"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("fn test_something() {\n    todo!()\n}\n")

        checker = RustChecker(CheckConfig())
        issues = checker._check_file_for_stubs(test_file)

        assert len(issues) == 0, "todo!() in test files should be exempt"

    def test_fixme_in_test_file_exempt(self, tmp_path):
        test_file = tmp_path / "test_bar.rs"
        test_file.write_text("// FIXME: needs better assertion\n")

        checker = RustChecker(CheckConfig())
        issues = checker._check_file_for_stubs(test_file)

        assert len(issues) == 0, "FIXME in test files should be exempt"
