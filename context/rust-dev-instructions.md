# Rust Development Tools

This bundle provides comprehensive Rust development capabilities for Amplifier.

## Available Tools

### rust_check

Run code quality checks on Rust files or projects.

```
rust_check(paths=["."])                    # Check current project
rust_check(paths=["src/"])                 # Check a directory
rust_check(paths=["src/main.rs"])          # Check a specific file
rust_check(checks=["lint"])                # Run only clippy
rust_check(checks=["format", "lint"])      # Run format + lint
```

**Checks performed:**
- **cargo fmt**: Code formatting (rustfmt style)
- **clippy**: Linting rules (clippy::all warnings)
- **cargo check**: Compile errors and type checking
- **stub detection**: `todo!()`, `unimplemented!()`, TODO/FIXME/HACK comments

### LSP Tools (via rust-analyzer)

Semantic code intelligence for Rust:

| Tool | Use For |
|------|---------|
| `hover` | Get type info, docs, and trait bounds |
| `goToDefinition` | Find where a symbol is defined |
| `findReferences` | Find all usages of a symbol |
| `goToImplementation` | Find trait implementors |
| `incomingCalls` | What calls this function? |
| `outgoingCalls` | What does this function call? |
| `codeAction` | Get suggested fixes from rust-analyzer |
| `customRequest` | Expand macros, find related tests |

## Automatic Checking Hook

When enabled, Rust files are automatically checked after write/edit operations.

**Behavior:**
- Triggers on `write_file`, `edit_file`, and similar tools
- Checks `*.rs` files only
- Runs lint and compile checks (fast subset)
- Injects issues into agent context for awareness

**Configuration** (in `Cargo.toml`):
```toml
[package.metadata.amplifier-rust-dev.hook]
enabled = true
file_patterns = ["*.rs"]
report_level = "warning"  # error | warning | info
auto_inject = true
```

## Configuration

Configure via `Cargo.toml`:

```toml
[package.metadata.amplifier-rust-dev]
# Enable/disable specific checks
enable_cargo_fmt = true
enable_clippy = true
enable_cargo_check = true
enable_stub_check = true

# Paths to exclude
exclude_patterns = [
    "target/**",
    ".git/**",
]

# Behavior
fail_on_warning = false

[package.metadata.amplifier-rust-dev.hook]
enabled = true
file_patterns = ["*.rs"]
report_level = "warning"
auto_inject = true
```

For workspaces, use `[workspace.metadata.amplifier-rust-dev]` instead.

## Best Practices

See @rust-dev:context/RUST_BEST_PRACTICES.md for the full development philosophy.

**Key points:**
1. Run `rust_check` after writing Rust code
2. Fix clippy warnings immediately - they catch real bugs
3. Use LSP tools to understand code before modifying
4. Let the type system guide correctness
5. Prefer `Result` over `unwrap()` in production code
