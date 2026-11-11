# changelog
Format: Keep a Changelog. semver. Rules: references/versioning.md.

## [Unreleased]
### Added
- `todoist plan|diff|commit`: two-way Todoist mirror. Sync-time user-lang title (<=12 words) + structured description (qué/por qué/quién/fechas/depende/origen) from line, note, goal, decisions, deps, blocks; key footer `T-xxxx · ctx`. Text cached per vault fingerprint (regenerated only on change). Read back as proposals: new comments, description/title edits, due/priority changes, completed, deleted. User edits never overwritten until `--ack`. Reopen when vault task reopened after we closed it
- `checklist` cmd: static action page per ctx (mine overdue/next 14 days/no date + others overdue; follow-ups and doing only when due), project label + group/filter by project, answer box per item, copy changes back; user-lang text cached in `.pro-assistant/cache/` via `--missing`/`--human`
- `<ctx>/_glossary.md`: labels expanded by pa.py and rejected by lint, terms sent to subagent; `validate` warns on opaque labels in open tasks
- view opens with Status pending+doing and dates = week
- `on` intent with `--date`; lint requires every other person named on today/on answers
- `sprints` intent: sprint plans parsed from index.md, owner and state from cited tasks; `model` exposes them
- lint: `avoid:` terms and missing sprint end dates; response templates carry an abbreviation glossary
### Fixed
- human payload listed finished tasks as blockers; waits_on now holds open tasks only
### Changed
- Todoist no longer one-way: md stays truth, Todoist edits enter as confirmed proposals
- subagent model: Sonnet; Spanish reads better and stays on the asked date, cost accepted
- every answer goes through the subagent; `ask --raw` = plain Python text for debug
- response templates rewritten as an assistant voice; never hide tasks
- humanizer: orchestrator never edits subagent text; lint runs on the final text

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
