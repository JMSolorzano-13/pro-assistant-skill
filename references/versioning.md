# versioning
Skill semver MAJOR.MINOR.PATCH. Source = `VERSION` file (= SKILL.md `version`). Log = CHANGELOG.md.
Vault stores `schema` (int, vault format) + `skill_version` in `.pro-assistant/config.md`.

## bump rules
- PATCH: wording/bugfix, no vault change.
- MINOR: new feature, vault-compatible.
- MAJOR: breaking skill behavior. Bump `SCHEMA` in pa.py when vault format changes in a way older readers cannot ignore (file layout, required line fields, fm keys); optional fields do not bump + add MIGRATIONS[old] step. Schema bump => MAJOR (or MINOR pre-1.0).
- Release: edit VERSION + SKILL.md version + CHANGELOG (same commit). Tag `vX.Y.Z`.

## runtime
- `pa.py version` -> skill + vault versions.
- `validate` flags: schema < skill -> ERR run upgrade | schema > skill -> ERR update skill | skill_version lower -> WARN run upgrade | higher -> WARN update skill.
- Upgrade flow: show validate msg -> confirm -> `pa.py --vault V upgrade` -> `validate`. Upgrade runs migrations in order, then sets skill_version. Never touch task text/ids beyond migration spec.
- Vault newer than skill: do not write. Tell user update skill.

## compat
- schema 1 -> 2 (v0.2.0): additive (`dep:`, `st:doing`, `view_port`, `refresh_min`). `upgrade` bumps config only. Old md valid as is.
- v0.5.0: optional task fields `pkg:`, `stage:`, `rel:`, `dup_of:`. No schema bump: older readers ignore them, no vault must change.
