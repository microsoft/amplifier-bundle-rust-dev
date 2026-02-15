# Rust LSP Context

You have access to Rust code intelligence via the LSP tool with rust-analyzer.

## Quick Start - Most Useful Operations

| Want to... | Use this |
|------------|----------|
| See type of a variable | `hover` on the variable |
| Find all usages of a symbol | `findReferences` on the symbol |
| Jump to a definition | `goToDefinition` on a call site or use statement |
| Find trait implementors | `goToImplementation` on a trait name |
| See what calls a function | `incomingCalls` on the function |
| See what a function calls | `outgoingCalls` on the function |
| List symbols in a file | `documentSymbol` on the file |
| Search symbols across workspace | `workspaceSymbol` with a query |
| Check for errors | `diagnostics` on a file |
| Rename a symbol safely | `rename` on the symbol |
| Get suggested fixes | `codeAction` at a diagnostic location |
| See inferred types in bulk | `inlayHints` on a range |
| Expand a macro | `customRequest` with `rust-analyzer/expandMacro` |
| Find related tests | `customRequest` with `rust-analyzer/relatedTests` |

**Tip**: `hover` and `goToImplementation` are the most powerful starting points for Rust. Start with these.

## Preflight Check

If LSP operations return errors, check rust-analyzer is installed:
```bash
rust-analyzer --version
```
If not found, install: `rustup component add rust-analyzer` or download standalone from https://github.com/rust-lang/rust-analyzer/releases

## Rust-Specific Capabilities

- **Trait Resolution**: Navigate trait hierarchies with `goToImplementation` and `findReferences` (note: `prepareTypeHierarchy`/`supertypes`/`subtypes` are NOT supported by rust-analyzer — use `goToImplementation` to find trait implementors and `findReferences` for broader type relationship discovery)
- **Macro Expansion**: See what macros expand to via `customRequest` with `rust-analyzer/expandMacro`
- **Cargo Workspace**: Understands multi-crate workspaces, cross-crate references
- **Clippy Integration**: Diagnostics include clippy lints alongside compiler errors
- **Lifetime/Borrow Info**: Inlay hints show lifetime annotations and borrow information
- **Proc Macro Support**: Analyzes proc macro expansions when crates are compiled

## When to Use LSP vs grep

| Task | Use LSP | Use grep |
|------|---------|----------|
| Find where a function is defined | `goToDefinition` (precise) | May match comments/strings |
| Find all callers of a function | `incomingCalls` (semantic) | Matches text, not calls |
| Get type of a variable | `hover` (inferred types) | Cannot do this |
| Find trait implementors | `goToImplementation` (precise) | Unreliable with generics |
| Search for text pattern | Too specific | `grep` (fast, broad) |
| Find files by name | Not applicable | `glob` (fast) |
| Rename a symbol safely | `rename` (all references) | May miss or over-match |
| Check for compiler errors | `diagnostics` (real errors) | Cannot do this |
| Expand a macro | `customRequest` | Cannot do this |

**Rule**: Use LSP for semantic code understanding (types, references, call chains, implementations). Use grep for text pattern matching.

## When to Delegate to code-intel

For simple single-operation lookups, use tool-lsp directly. **Delegate to `code-intel` for**:
- Complex multi-step navigation ("trace all implementations of this trait across crates")
- Type system questions ("what trait bounds constrain this generic?")
- Macro debugging ("what does this derive macro generate?")
- Module dependency mapping across a workspace
- When deep Rust expertise is needed alongside LSP operations

## customRequest Quick Reference (rust-analyzer Extensions)

| Method | Description |
|--------|-------------|
| `rust-analyzer/expandMacro` | Expand a macro at cursor position (standalone build only — not available in rustup component) |
| `rust-analyzer/relatedTests` | Find tests related to a function/struct (standalone build only — not available in rustup component) |
| `experimental/externalDocs` | Get docs.rs or std library doc links |
| `experimental/runnables` | Find runnable targets (tests, bins, examples) |
| `rust-analyzer/fetchDependencyList` | List all crate dependencies |
| `experimental/ssr` | Structural search and replace |
| `rust-analyzer/viewRecursiveMemoryLayout` | Inspect memory layout of a type |

## Workspace Detection

The Rust LSP detects workspace root by looking for:
- Cargo.toml (preferred)
- Cargo.lock
- .git directory

Ensure your project has a `Cargo.toml` at the root for accurate analysis. For Cargo workspaces, rust-analyzer reads the workspace `Cargo.toml` and understands all member crates.

## Installation

rust-analyzer can be installed two ways:

**Standalone (REQUIRED for expandMacro, relatedTests, and other custom extensions):**
Download from https://github.com/rust-lang/rust-analyzer/releases
- Includes all custom extensions (expandMacro, relatedTests, runnables, etc.)

**Via rustup (simpler — but custom extensions like expandMacro will NOT work):**
```bash
rustup component add rust-analyzer
```
- The rustup version may lag behind standalone releases
- Custom extensions (expandMacro, relatedTests, externalDocs) are NOT available in the rustup build
- All standard LSP operations (hover, goToDefinition, findReferences, etc.) work fine with either build

Verify installation:
```bash
rust-analyzer --version
```

## Persistent Server

rust-analyzer runs as a persistent background service via a lightweight proxy.
This eliminates cold-start indexing delay for subsequent sessions on the same project.

**How it works:**
- First session: rust-analyzer starts and indexes the workspace (may take 30-90 seconds for large projects)
- Subsequent sessions: connect to the already-warm server instantly
- Sub-agent delegations (code-intel): also connect to the warm server
- After 5 minutes with no active sessions, the server shuts down automatically

**Controlling the server:**
- Servers are scoped per project directory — each workspace gets its own rust-analyzer instance
- State files at `~/.amplifier/lsp-servers/` track running servers
- To force a fresh server, delete the state file for your project and start a new session
- To change the idle timeout, configure `idle_timeout` in your bundle's server config

**Checking server status:**
```bash
ls ~/.amplifier/lsp-servers/rust-*.json
cat ~/.amplifier/lsp-servers/rust-*.json  # Shows PID, port, workspace
```

**If the server seems stale or unresponsive:**
1. Delete the state file: `rm ~/.amplifier/lsp-servers/rust-*.json`
2. Start a new session — a fresh server will be created

## Known Limitations

### workspaceSymbol May Return Empty
Returns empty results due to rust-analyzer indexing lifecycle. Use `documentSymbol` per-file or grep for workspace-wide symbol search.
- **Workaround**: Run `documentSymbol` on relevant files first, wait 2-3 seconds, then retry `workspaceSymbol`.

### Proc Macro Expansion Requires Build
Proc macro crates must be compiled before rust-analyzer can expand them:
- **Workaround**: Run `cargo build` or `cargo check` to compile proc macro crates. Check that `target/` exists.

### Slow Initial Indexing on Large Workspaces
Very large Cargo workspaces may take time for initial indexing:
- **Workaround**: Wait for rust-analyzer to finish loading. First operations may be slow; subsequent ones will be fast.

### Build Script Output
Code generated by `build.rs` requires the `target/` directory:
- **Workaround**: Run `cargo check` to generate build script output before using LSP on generated types.

### Type Hierarchy Not Supported
rust-analyzer does not implement `prepareTypeHierarchy`/`supertypes`/`subtypes`. The server returns "unknown request" for these operations.
- **Workaround**: Use `goToImplementation` to find trait implementors. Use `findReferences` for broader type relationship discovery.

### Async Call Hierarchy Limitations
`incomingCalls`/`outgoingCalls` may return empty results for `async fn`. This is a rust-analyzer limitation — trait method dispatch through generics is not tracked.
- **Workaround**: Use `findReferences` as fallback for tracing async function usage.

### Cold-Start Indexing (mitigated by persistent server)
The persistent server eliminates cold-start for subsequent sessions. First session on a new workspace still needs rust-analyzer to index (30-90 seconds for large projects). If the server was idle for >5 minutes, it auto-shut down and will need to restart.
- **Workaround**: Check `ls ~/.amplifier/lsp-servers/rust-*.json` to see if a warm server exists. Retry if you get empty results on first try. Run `diagnostics` on a file to trigger analysis.

### Code Actions Require Indexed Workspace
`codeAction` may return empty if the workspace hasn't finished indexing.
- **Workaround**: Try `diagnostics` first to trigger analysis, then `codeAction`.

### Custom Extensions (expandMacro, relatedTests)
May not be available in the rustup component version. Install standalone rust-analyzer from GitHub releases for full extension support.
- **Workaround**: If `expandMacro` or `relatedTests` returns "Method not supported", install the standalone build from https://github.com/rust-lang/rust-analyzer/releases.

## Troubleshooting

### "rust-analyzer not found"
1. **Check**: `rust-analyzer --version`
2. **Install**: `rustup component add rust-analyzer`
3. **Verify**: Ensure `~/.cargo/bin` is in your PATH

### Slow or Missing Results
1. **Check**: rust-analyzer may still be indexing (check `diagnostics` output)
2. **Fix**: Wait for indexing to complete, or run `cargo check` to warm up
3. **Verify**: `documentSymbol` returns results on known files

### Proc Macro Errors
1. **Check**: `cargo build` succeeds for proc macro crates
2. **Fix**: Ensure `target/` directory exists and is current
3. **Verify**: `hover` on derived items shows expanded types

### Missing Cross-Crate References
1. **Check**: Root `Cargo.toml` lists all workspace members
2. **Fix**: Ensure all crates are part of the workspace
3. **Verify**: `goToDefinition` navigates across crate boundaries
