# Changelog

All notable changes to this project are documented in this file.

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
