# changelog
Format: Keep a Changelog. semver. Rules: references/versioning.md.

## [0.5.0] - 2026-11-06
### Added
- `ask`: single read entry; Python answers list intents without a model, subagent only for judgement
- `graph` (in-memory, transitive impact, `unblock` intent) and `dupes` (dup vs stage candidates)
- `apply`: update, set, merge, undo, --json; restores on validate failure, keeps CRLF and field placement
- task fields `pkg:`, `stage:`, `rel:`, `dup_of:`; brief collapses a pkg to its active stage
### Changed
- vault schema stays 2: new fields are optional and ignored by older readers
- `check` also matches same verb + same work across abbreviations; `validate` warns on possible dups
- SKILL.md, intents, agents, dedupe, humanizer reduced: facts move to Python
### Removed
- output contract v1 and references/output-contract.md: all use is chat with the skill

## [0.4.0] - 2026-11-06
### Added
- backend/frontend split: subagent `pro-assistant-executive` writes final answers from an id-free payload
- pa.py: `brief` (compact projection), `apply` (dry-run writes, natural preview, validate after write), `compose` (subagent input), `prefs` (allow-listed overlay, undo), `lint-output` (leak, date, unconfirmed gate)
- templates/responses.md, references/humanizer.md, Mermaid diagrams with natural labels (max 12 nodes)
- tests/: unittest suite + token measurement
### Changed
- subagent stays on Haiku: Sonnet cost ~16x with no factual gain on tests/eval_humanizer.py
- output contract v1 is machine channel only (Raycast); schema unchanged (2), run `upgrade` to record version

## [0.3.0] - 2026-10-18
### Added
- view: date combo with auto ranges: today, week (Mon-Sun), current Q, next Q. Recomputed on refresh. Manual from/to resets combo.

## [0.2.0] - 2026-10-18
### Added
- read-only local view (port 8013, 127.0.0.1): task deps, timeline, project deps; filters ctx/project/status/owner/pri/dates/overdue/critical path/archived/text; auto-refresh 30 min; ES/EN UI
- pa.py: `model`, `view`, `open`
- task field `dep:` (validated: unknown ref, self, cycle); status `doing`
- config `view_port`, `refresh_min`
- references/view.md, references/adopt.md
### Changed
- vault schema 1 -> 2 (additive; `upgrade` migrates)
- write_cfg no longer bumps schema/skill_version on init/sync of older vaults

## [0.1.0] - 2026-10-16
### Added
- init, sync-contexts, intent router, 6 agents + onboarding, output contract v1
- classify: project vs light item vs reminder; promote after 3 same-topic items
- dedupe guard: `check`, `new-project` refuse dup, `validate` dup rules
- optional Todoist mirror (md = truth)
- pa.py: version, init, sync, validate, next-id, check, new-project, upgrade
- vault schema 1; versioning + upgrade path
