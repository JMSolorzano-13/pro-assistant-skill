# dedupe (CRITICAL)
Never duplicate project or active task. `apply add` + `new-project` enforce; `check` only for minute items/promote.
`check --ctx C --text T [--topic X]`: PROJECT_MATCH -> use it. ARCHIVED_MATCH -> offer reactivate. TASK_MATCH -> show; update | merge | skip | add differentiated only if user insists. NONE -> safe. Exit 10 = match.
`new-project` refuses dup (exit 2); `--force` only after explicit OK.

## invariants
1 One task = one place (project actions.md XOR tracker.md). Promote = move.
2 ids via `next-id`/apply: global unique, never reuse.
3 Project name+alias+slug unique among open projects per ctx. Alt name -> add alias.
4 Task in archived project never open: close or move.
5 Minutes: each commitment individually `check`ed. Match -> append `src`, list "already tracked", no new task.
6 Todoist: 1 task <-> 1 td id. search T-id before create (todoist.md).
7 Cross-ctx: check per ctx.
8 Batch: compare also against earlier items in batch.
9 `validate`: `dup ...` errors must be 0. `possible dup` warning -> dupes flow (humanizer.md).

## merge
`apply merge --task <keep> --drop <other>`: other -> st:cancelled + dup_of; deps moved to keep; dependents re-pointed; line stays. td of other -> TODOIST_SYNC.
