# Rust Development Philosophy

This document outlines the core development principles for Rust code in the Amplifier ecosystem.

## Core Philosophy: Safe, Idiomatic, Complete

We value **correctness over cleverness**, **completion over ambition**, and **leveraging the type system over runtime checks**.

---

## The Six Principles

### 1. Ownership Clarity

Make borrowing patterns obvious. When ownership is confusing, the code is confusing.

- **Prefer borrowing over cloning**: Clone only when necessary, not to silence the borrow checker
- **Lifetime annotations**: Add when the compiler asks; they document data flow
- **Smart pointers**: `Box`, `Rc`, `Arc` each serve specific purposes — choose deliberately
- **Interior mutability**: `RefCell`/`Mutex` signal shared mutable state — make it obvious

**Test**: *"Can a new team member trace who owns this data?"*

### 2. Complete or Not At All

Production code should be **finished**. These patterns indicate incomplete code:

| Pattern | What It Signals |
|---------|-----------------|
| `todo!()` | Unfinished implementation |
| `unimplemented!()` | Missing functionality (unless trait default with docs) |
| `// TODO:` / `// FIXME:` | Deferred work |
| `.unwrap()` in non-test code | Unhandled error case |
| `// HACK:` | Acknowledged technical debt |
| `panic!()` in library code | Unrecoverable where recovery is possible |

**Key insight**: Every `todo!()` is a runtime bomb waiting for production.

**Legitimate exceptions**:
- `unreachable!()` in exhaustive match arms (safety assertion)
- `unimplemented!()` in trait default implementations with doc comments
- `todo!()` and `// TODO` in test files
- `.unwrap()` in tests and examples
- `panic!()` for truly unrecoverable states (OOM, corrupted invariants)

### 3. Let the Compiler Help

Rust's type system is your ally. Use it for correctness, not just compliance.

- **Newtypes**: Wrap primitives to prevent mixing (`UserId(u64)` vs raw `u64`)
- **Enums over booleans**: `Mode::Read` / `Mode::Write` over `is_read: bool`
- **Builder pattern**: For complex construction with validation
- **Type state**: Compile-time state machine enforcement when appropriate

**Test**: *"Can the compiler catch this mistake before runtime?"*

### 4. Error Handling is Communication

Errors tell the caller what went wrong and what they can do about it.

- **Use `Result<T, E>`**: Not `panic!()`, not `.unwrap()`
- **Custom error types**: `thiserror` for libraries, `anyhow` for applications
- **The `?` operator**: Propagate errors cleanly up the call stack
- **Error context**: Use `.context()` (anyhow) or `.map_err()` to add information
- **Never `unwrap()` in library code**: The caller deserves a `Result`

### 5. Idiomatic Patterns

Follow Rust community conventions for predictable, readable code.

- **Iterator chains over loops**: When they read naturally
- **Pattern matching**: Use `match` and `if let` over nested `if` chains
- **Derive what you can**: `#[derive(Debug, Clone, PartialEq)]` for data types
- **Module organization**: `mod.rs` or `module/mod.rs` — pick one pattern per project
- **Documentation**: `///` for public items, `//!` for module-level docs

**Test**: *"Would this look at home in a well-regarded Rust crate?"*

### 6. Performance Awareness, Not Premature Optimization

Rust's zero-cost abstractions mean you rarely need to sacrifice clarity.

- **Profile before optimizing**: Don't guess where the bottleneck is
- **Prefer stack over heap**: But not at the cost of readability
- **Avoid unnecessary allocations**: `&str` over `String` in function parameters
- **Iterators over collected vectors**: Process lazily when possible

---

## The Golden Rule

> Write code as if the next person to read it is fighting the borrow checker at 2 AM during an incident. Make ownership obvious, errors recoverable, and intent clear.

---

## Quick Reference

### Always Do
- Handle errors with `Result` and `?`
- Add `#[derive(Debug)]` to all public types
- Use `clippy` warnings as guidance
- Document public APIs with `///` doc comments
- Run `cargo fmt` before committing

### Never Do
- Leave `todo!()` in production code
- Use `.unwrap()` in library code
- Silence clippy with `#[allow(...)]` without a comment explaining why
- Use `unsafe` without a `// SAFETY:` comment
- Catch-all error types (`Box<dyn Error>`) in libraries

### Consider Context
- `.unwrap()`: Fine in tests and quick prototypes, not in production
- `clone()`: Sometimes clarity beats performance
- `unsafe`: Necessary for FFI and some optimizations — document invariants
- Macros: Use when they reduce boilerplate significantly, not for cleverness
