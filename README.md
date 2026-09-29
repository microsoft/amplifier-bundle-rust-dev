# amplifier-bundle-rust-dev

Comprehensive Rust development tools for Amplifier.

Provides:
- **LSP integration** — rust-analyzer for code intelligence
- **Code quality** — cargo fmt, clippy, cargo check integration
- **Auto-checking** — hooks that run on file write/edit
- **Stub detection** — identifies todo!(), unimplemented!(), // TODO patterns
- **Expert agents** — rust-dev (quality) + code-intel (LSP navigation)

## Security and workspace trust

Rust build scripts, procedural macros, dependencies, Cargo subcommands, and
language-server features can execute native code. This bundle therefore uses
a restricted default profile:

- rust-analyzer build scripts, procedural macros, and check-on-save are disabled.
- rust-analyzer custom requests are disabled.
- Automatic edit hooks run only non-executing stub checks.
- `rust_check` skips Cargo-based checks until the host process sets
  `AMPLIFIER_RUST_ALLOW_WORKSPACE_EXECUTION=true`.
- Cargo commands run only from the canonical configured workspace root and
  reject paths outside it.
- Compiler diagnostics are XML-escaped and labeled as untrusted data before
  they are added to model context.
- External Git sources are pinned to reviewed immutable revisions.

Enabling workspace execution is a security decision. Do it only after trusting
the repository, its dependencies, `build.rs` files, procedural macros, Cargo,
rust-analyzer, rustfmt, Clippy, and the Rust toolchain. Repository-controlled
Cargo metadata cannot enable this setting.

### Migration from 0.2.x behavior defaults

Existing consumers that require automatic Cargo checks must set
`AMPLIFIER_RUST_ALLOW_WORKSPACE_EXECUTION=true` in the host process for each
trusted workspace and restore the desired `format`, `lint`, or `types` checks.
Do not put this value in repository configuration or a repository `.env` file.
For LSP features that require generated code or procedural macros, provide a
separate trusted override enabling the relevant rust-analyzer options.
Untrusted workspaces remain intentionally limited.

## Usage

```yaml
includes:
  - bundle: git+https://github.com/microsoft/amplifier-bundle-rust-dev@main
```

## Individual Behaviors

```yaml
# LSP only (no quality hooks):
includes:
  - bundle: rust-dev:behaviors/rust-lsp

# Quality tools only:
includes:
  - bundle: rust-dev:behaviors/rust-quality
```

## License

This project is licensed under the MIT License.

## Contributing

> [!NOTE]
> This project is not currently accepting external contributions, but we're actively working toward opening this up. We value community input and look forward to collaborating in the future. For now, feel free to fork and experiment!

Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit [Contributor License Agreements](https://cla.opensource.microsoft.com).

When you submit a pull request, a CLA bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft
trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.
