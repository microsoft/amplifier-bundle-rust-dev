"""Validate rust-dev bundle composition."""

from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent


def deep_merge(base, overlay):
    result = base.copy()
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


# -- LSP behavior tests (adapted from lsp-rust) ---------------------


class TestRustLspBehavior:
    """Tests for the rust-lsp behavior (absorbed from lsp-rust)."""

    def test_rust_config_merges(self):
        """Rust language config merges into lsp-core's empty languages slot."""
        behavior = yaml.safe_load((ROOT / "behaviors" / "rust-lsp.yaml").read_text())
        rust_config = next(t["config"] for t in behavior["tools"] if t["module"] == "tool-lsp")
        core_config = {"languages": {}, "timeout_seconds": 30}
        merged = deep_merge(core_config, rust_config)
        assert "rust" in merged["languages"]
        assert merged["languages"]["rust"]["extensions"] == [".rs"]
        assert merged["languages"]["rust"]["server"]["command"] == ["rust-analyzer"]
        assert merged["timeout_seconds"] == 30

    def test_rust_server_config_complete(self):
        """Rust server config has all required fields."""
        behavior = yaml.safe_load((ROOT / "behaviors" / "rust-lsp.yaml").read_text())
        rust = next(t["config"] for t in behavior["tools"] if t["module"] == "tool-lsp")["languages"]["rust"]
        assert "extensions" in rust
        assert "workspace_markers" in rust
        assert "server" in rust
        assert "command" in rust["server"]
        assert "install_check" in rust["server"]
        assert "install_hint" in rust["server"]

    def test_rust_capabilities_declared(self):
        """Rust bundle declares supported capabilities."""
        behavior = yaml.safe_load((ROOT / "behaviors" / "rust-lsp.yaml").read_text())
        caps = next(t["config"] for t in behavior["tools"] if t["module"] == "tool-lsp")["languages"]["rust"][
            "capabilities"
        ]
        assert caps.get("diagnostics") is True
        assert caps.get("rename") is True
        assert caps.get("codeAction") is True
        assert caps.get("inlayHints") is True
        assert caps.get("customRequest") is True
        assert caps.get("goToImplementation") is True

    def test_rust_lifecycle_config(self):
        """Rust server config should have lifecycle and idle_timeout."""
        behavior = yaml.safe_load((ROOT / "behaviors" / "rust-lsp.yaml").read_text())
        server = next(t["config"] for t in behavior["tools"] if t["module"] == "tool-lsp")["languages"]["rust"][
            "server"
        ]
        assert server.get("lifecycle") == "timeout"
        assert server.get("idle_timeout") == 300

    def test_lsp_behavior_references_rust_dev_namespace(self):
        """LSP behavior should reference rust-dev namespace, not lsp-rust."""
        behavior = yaml.safe_load((ROOT / "behaviors" / "rust-lsp.yaml").read_text())
        # Context should reference rust-dev:
        context_includes = behavior.get("context", {}).get("include", [])
        assert any("rust-dev:" in c for c in context_includes)
        assert not any("lsp-rust:" in c for c in context_includes)
        # Agent should reference rust-dev:
        agent_includes = behavior.get("agents", {}).get("include", [])
        assert any("rust-dev:" in a for a in agent_includes)


# -- Quality behavior tests -----------------------------------------


class TestRustQualityBehavior:
    """Tests for the rust-quality behavior."""

    def test_quality_behavior_has_tool(self):
        """Quality behavior declares tool-rust-check."""
        behavior = yaml.safe_load((ROOT / "behaviors" / "rust-quality.yaml").read_text())
        tools = behavior.get("tools", [])
        assert any(t["module"] == "tool-rust-check" for t in tools)

    def test_quality_behavior_has_hook(self):
        """Quality behavior declares hooks-rust-check."""
        behavior = yaml.safe_load((ROOT / "behaviors" / "rust-quality.yaml").read_text())
        hooks = behavior.get("hooks", [])
        assert any(h["module"] == "hooks-rust-check" for h in hooks)

    def test_quality_behavior_has_agent(self):
        """Quality behavior registers the rust-dev agent."""
        behavior = yaml.safe_load((ROOT / "behaviors" / "rust-quality.yaml").read_text())
        agents = behavior.get("agents", {}).get("include", [])
        assert any("rust-dev" in a for a in agents)

    def test_quality_behavior_has_context(self):
        """Quality behavior includes instructions context."""
        behavior = yaml.safe_load((ROOT / "behaviors" / "rust-quality.yaml").read_text())
        context = behavior.get("context", {}).get("include", [])
        assert any("rust-dev-instructions" in c for c in context)


# -- Composite behavior tests ---------------------------------------


class TestRustDevBehavior:
    """Tests for the rust-dev composite behavior."""

    def test_composite_includes_lsp(self):
        """Composite behavior includes rust-lsp behavior."""
        behavior = yaml.safe_load((ROOT / "behaviors" / "rust-dev.yaml").read_text())
        includes = behavior.get("includes", [])
        assert any("rust-lsp" in str(i) for i in includes)

    def test_composite_includes_quality(self):
        """Composite behavior includes rust-quality behavior."""
        behavior = yaml.safe_load((ROOT / "behaviors" / "rust-dev.yaml").read_text())
        includes = behavior.get("includes", [])
        assert any("rust-quality" in str(i) for i in includes)

    def test_composite_has_no_direct_tools(self):
        """Composite behavior should only include sub-behaviors, not define tools."""
        behavior = yaml.safe_load((ROOT / "behaviors" / "rust-dev.yaml").read_text())
        assert "tools" not in behavior, "Composite should not define tools directly"
        assert "hooks" not in behavior, "Composite should not define hooks directly"


# -- Bundle metadata tests ------------------------------------------


class TestBundleMetadata:
    """Tests for the root bundle.yaml."""

    def test_bundle_name(self):
        """Root bundle has correct name."""
        bundle = yaml.safe_load((ROOT / "bundle.yaml").read_text())
        assert bundle["bundle"]["name"] == "rust-dev"

    def test_bundle_has_version(self):
        """Root bundle has a version."""
        bundle = yaml.safe_load((ROOT / "bundle.yaml").read_text())
        assert "version" in bundle["bundle"]

    def test_bundle_includes_composite(self):
        """Root bundle includes the composite behavior."""
        bundle = yaml.safe_load((ROOT / "bundle.yaml").read_text())
        includes = bundle.get("includes", [])
        assert any("rust-dev" in str(i) for i in includes)

    def test_bundle_uses_internal_composite(self):
        """bundle.yaml includes the internal composite behavior."""
        bundle = yaml.safe_load((ROOT / "bundle.yaml").read_text())
        includes = bundle["includes"]
        assert len(includes) == 1
        assert includes[0]["bundle"] == "rust-dev:behaviors/rust-dev"


# -- Agent tests -----------------------------------------------------


class TestAgents:
    """Tests for agent files."""

    def test_code_intel_agent_name(self):
        """code-intel agent has correct name in frontmatter."""
        content = (ROOT / "agents" / "code-intel.md").read_text()
        parts = content.split("---", 2)
        assert len(parts) >= 3
        meta = yaml.safe_load(parts[1])
        assert meta["meta"]["name"] == "code-intel"

    def test_code_intel_agent_has_lsp_tool(self):
        """code-intel agent declares tool-lsp."""
        content = (ROOT / "agents" / "code-intel.md").read_text()
        parts = content.split("---", 2)
        meta = yaml.safe_load(parts[1])
        assert any(t["module"] == "tool-lsp" for t in meta["tools"])

    def test_rust_dev_agent_name(self):
        """rust-dev agent has correct name in frontmatter."""
        content = (ROOT / "agents" / "rust-dev.md").read_text()
        parts = content.split("---", 2)
        meta = yaml.safe_load(parts[1])
        assert meta["meta"]["name"] == "rust-dev"

    def test_rust_dev_agent_has_both_tools(self):
        """rust-dev agent declares both tool-rust-check and tool-lsp."""
        content = (ROOT / "agents" / "rust-dev.md").read_text()
        parts = content.split("---", 2)
        meta = yaml.safe_load(parts[1])
        modules = [t["module"] for t in meta["tools"]]
        assert "tool-rust-check" in modules
        assert "tool-lsp" in modules

    def test_code_intel_has_prerequisite_validation(self):
        """code-intel agent includes prerequisite validation section."""
        content = (ROOT / "agents" / "code-intel.md").read_text()
        assert "## Prerequisite Validation" in content

    def test_rust_dev_agent_description_mentions_quality(self):
        """rust-dev agent description mentions code quality."""
        content = (ROOT / "agents" / "rust-dev.md").read_text()
        parts = content.split("---", 2)
        meta = yaml.safe_load(parts[1])
        desc = meta["meta"]["description"].lower()
        assert "quality" in desc or "linting" in desc or "formatting" in desc


# -- Context file tests -----------------------------------------------


class TestContext:
    """Tests for context files."""

    def test_rust_lsp_context_exists(self):
        """rust-lsp.md context file exists."""
        assert (ROOT / "context" / "rust-lsp.md").exists()

    def test_rust_lsp_context_no_old_namespace(self):
        """rust-lsp.md should not reference old lsp-rust namespace."""
        content = (ROOT / "context" / "rust-lsp.md").read_text()
        # The agent delegation section should reference code-intel, not rust-code-intel
        assert "rust-code-intel" not in content

    def test_rust_dev_instructions_exists(self):
        """rust-dev-instructions.md context file exists."""
        assert (ROOT / "context" / "rust-dev-instructions.md").exists()

    def test_rust_best_practices_exists(self):
        """RUST_BEST_PRACTICES.md context file exists."""
        assert (ROOT / "context" / "RUST_BEST_PRACTICES.md").exists()

    def test_rust_lsp_context_has_preflight(self):
        """Rust LSP context includes preflight check section."""
        content = (ROOT / "context" / "rust-lsp.md").read_text()
        assert "## Preflight Check" in content


# -- Namespace consistency tests ----------------------------------------


class TestNamespaceConsistency:
    """No stale lsp-rust: namespace references."""

    def test_no_lsp_rust_namespace_in_behaviors(self):
        """No behavior file should reference the old lsp-rust: namespace."""
        for yaml_file in (ROOT / "behaviors").glob("*.yaml"):
            content = yaml_file.read_text()
            assert "lsp-rust:" not in content, f"{yaml_file.name} still references lsp-rust: namespace"

    def test_no_lsp_rust_namespace_in_agents(self):
        """No agent file should reference the old lsp-rust: namespace."""
        for md_file in (ROOT / "agents").glob("*.md"):
            content = md_file.read_text()
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                assert "lsp-rust:" not in frontmatter, f"{md_file.name} frontmatter references lsp-rust: namespace"


# -- YAML validity tests ------------------------------------------------


class TestYamlValidity:
    """All YAML files should parse without error."""

    def test_all_yaml_valid(self):
        """All YAML files in the bundle parse correctly."""
        for yaml_file in ROOT.rglob("*.yaml"):
            # Skip hidden dirs and caches
            if any(part.startswith(".") or part == "node_modules" for part in yaml_file.parts):
                continue
            content = yaml.safe_load(yaml_file.read_text())
            assert content is not None, f"{yaml_file} is empty or invalid"


# -- File structure tests ------------------------------------------------


class TestFileStructure:
    """All expected files from the bundle are present."""

    def test_expected_files_exist(self):
        """All expected files are present."""
        expected = [
            "bundle.yaml",
            "pyproject.toml",
            "behaviors/rust-dev.yaml",
            "behaviors/rust-lsp.yaml",
            "behaviors/rust-quality.yaml",
            "agents/rust-dev.md",
            "agents/code-intel.md",
            "context/rust-dev-instructions.md",
            "context/rust-lsp.md",
            "context/RUST_BEST_PRACTICES.md",
        ]
        for path in expected:
            assert (ROOT / path).exists(), f"Missing expected file: {path}"
