# dedupe (CRITICAL)
Never create duplicate project or duplicate active task.

## before ANY create/add/promote/minute-extract
Run `pa.py --vault V check --ctx C --text "<EN text or project name>" [--topic X]`.
Output:
- PROJECT_MATCH <slug> -> open project exists. Use it. Add info/tasks there. Do NOT create.
- ARCHIVED_MATCH <slug> -> offer reactivate (status->active, note reason) instead of new.
- TASK_MATCH <T-id> in:<scope> -> same open task exists. Show it. Options: update fields | merge | skip | (only if user insists distinct) add with differentiating text.
- NONE -> safe.
Exit 10 = match found.
New project ONLY via `pa.py new-project` (refuses dup, exit 2). `--force` only after explicit user OK.

## invariants
1 One task = one place (project actions.md XOR tracker.md). Promote = move.
2 ids global unique via `pa.py next-id`. Compute id immediately before write; re-run for each task in batch.
3 Project name+alias+slug unique among open projects per ctx. Add alias when user uses alt name.
4 Task in archived project never open: close or move.
5 Minute processing: every extracted commitment passes `check` individually. Match -> link `src` to existing task (append `src`), no new task. Dup -> list under "Pending confirm" as "already tracked T-xxxx".
6 Todoist: 1 task <-> 1 td id. before create, search by T-id. See todoist.md.
7 Cross-ctx: check only inside ctx. User asks cross-ctx -> check each, report.
8 Batch writes: check each item against earlier items in same batch.
9 After writes: `pa.py validate`. `dup ...` errors must be 0.

## merge procedure
Keep older id. Merge fields (earliest created, latest due only if user confirms; union src). Mark other `st:cancelled` NOT delete only if it had td/ref; else remove line. Show diff.
