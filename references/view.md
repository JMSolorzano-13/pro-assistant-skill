# view
Read-only local page. Source = vault md ONLY (via `pa.py model`). No writes, no actions. Extra to Todoist, independent.

## cmds
- `pa.py --vault V open [--port N]` -> start server if down (detached) + open browser. default cmd for user.
- `pa.py --vault V view [--port N] [--open]` -> foreground server. port busy -> ERR; ours -> use `open`.
- `pa.py --vault V model` -> JSON projection (debug/verify).
Port: arg > config `view_port` > 8013. Bind 127.0.0.1 only. GET only. Auto-refresh page every config `refresh_min` (30).

## model (build_model)
ctxs[]{id,name(_context org),projects[],edges[[dep,proj]],tasks[],agenda[]}.
- project: index.md fm + risk_max/open risks (risks.md) + file.
- task: line fields + dep[] + project + file:line.
- agenda: tracker lines `YYYY-MM-DD | text | ref:T-xxxx`.
Nothing inferred. Missing field -> null. No dates -> shown, no date features. No dep -> no edge, node shown.

## views
dep = task DAG per ctx, columns by depth. time = axis by date, rows per project (+tracker, agenda), undated column. proj = project DAG (dep/blocks) + progress + risk badge.
First open (no saved link state): Status pending+doing and dates = week. Clear button empties all.
Filters: ctx, project, status, owner, pri, date combo (today|week Mon-Sun|current Q|next Q -> auto from/to; recomputed each refresh; manual from/to resets combo) + date range, overdue, critical path, archived, text. Click node = detail (read-only).
Status: pending|doing|blocked|proposed|done; dashed = waiting on deps; red = overdue.

## agent rules
- user asks diagram/timeline/dependencies visual -> small graph: compose diagram; full view -> run `open`, give URL. no extra explanation.
- page wrong/empty -> run `validate`, fix md (with confirm), never "fix" in page.
- tasks need `dep:` to draw task edges; ask user only if a dependency is stated and not stored.
