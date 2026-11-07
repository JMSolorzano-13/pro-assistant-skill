# adopt (existing vault or md)
Goal: bring existing md into current schema. Read-only first. No loss.

## case A: vault from this skill (config exists)
1 `pa.py version` + `validate`. schema/version lower -> show msg.
2 Confirm -> `pa.py upgrade` -> `validate`. Migrations never edit task text/ids. Done. No survey.
3 New optional fields (`dep:`, `st:doing`, view cfg) stay empty until user states them.

## case B: md not from this skill (other layout/format)
1 Ask root path. Scan read-only: list dirs, md files, frontmatter, task-like lines. Never write yet.
2 Map: dir -> ctx, subdir -> project, checkbox lines -> tasks, headings -> goal/state/risks. Show mapping table + gaps (no id, no owner, no due, no status, dup names).
3 Dedupe on mapped items (same rules as dedupe.md) before proposing.
4 Short survey ONLY for gaps that block validity: ctx names, project status, owners/dates marked `unknown`. Batch questions, <=8. Skip when optional.
5 Show plan (files created/changed, ids to assign via `next-id`). Confirm.
6 Run `init` (non-destructive). Write converted files; keep originals untouched (copy, not move) until user confirms swap.
7 `validate` -> 0 errors. Report counts.

## rules
- unknown stays `unknown`/blank. no invention.
- `confirmed:false` for converted free-text context.
- never overwrite existing user files without backup copy + confirm.
