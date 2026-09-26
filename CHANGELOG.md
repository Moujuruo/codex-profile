# Changelog

All notable changes to this project are documented in this file.

## Unreleased

- Save and switch the provider display name (`name`) per profile via
  `--provider-name` and interactive editing; include it in deduplication and
  external-change detection.
- Migrate older profiles using their provider table's current display name,
  preserving existing local-compaction compatibility settings.
- Record a per-profile `wire_api` (`responses` or `chat`) and write it to the
  active provider's `[model_providers.<id>]` table on every switch; the line is
  inserted when the table lacks it.
- Add `--wire-api` to `add` and `edit`, show `wire_api` in `list`, `current`,
  `use`, and the interactive menu, and include it in dedup/auto-save matching.
- Profiles saved by older versions default to `responses` on load.
- Insert missing provider fields correctly when `config.toml` has no final
  newline.
- Warn on stderr when a profile uses `wire_api = "chat"`, which current Codex
  releases reject at startup (openai/codex#7782); `chat` only works with older
  Codex versions.
- Return an actionable error immediately when another `codex-profile` instance
  holds the configuration lock, instead of waiting indefinitely.

## 1.1.0 - 2026-08-16

- Add a persistent numbered interactive menu as the default interface.
- Keep subcommands for scripting and automation.
- Add interactive add, switch, edit, rename, delete, inspect, and backup flows.
- Preserve hidden API-key input and hashed key identifiers.

## 1.0.0 - 2026-08-16

- Save and switch Codex `base_url` and API-key pairs.
- Automatically import the current configuration and deduplicate profiles.
- Detect external changes and preserve them as a new profile.
- Back up and atomically update `config.toml` and `auth.json`.
