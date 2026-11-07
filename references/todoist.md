# todoist (optional, off by default)
Purpose: user gets reminders in Todoist app. md = source of truth. Todoist = one-way mirror md -> Todoist. Skill never executes actions behind tasks.

## enable
config todoist:on only if user asked AND Todoist MCP tools present in session. Tools absent -> keep off, tell user, continue md-only. Never fail the flow because of Todoist.

## what to mirror
Only open tasks/reminders with `due`, or user-selected. Skip ideas w/o date unless asked. Never archived/done (done -> complete the td task if td set, with confirm).

## task shape (min words)
- title: <=6 words, verb first, EN or user lang if user prefers (UI only). e.g. "Send Alfa invoice".
- due: ISO date (time only if in md).
- project: Todoist project = md project name; light items -> Todoist project = ctx name. find existing first, create only if missing (check by exact name).
- description: `T-0001` only (+ ctx). Link key.
- priority: high->p1, med->p2, low->p4.

## dedupe (no dup in Todoist)
1 md line has `td:<id>` -> update that task, never create.
2 no td: search Todoist for `T-xxxx` in description (and exact title+due). found -> write td id to md, no create.
3 not found -> create, then write `td:<id>` to task line.
4 `validate` errors on dup td ids.
5 batch: show list (create/update/skip) -> confirm -> apply.

## sync rules
- md changes (due, done, cancelled, renamed) -> propose matching Todoist update, confirm.
- Todoist-side edits not read back (v1). state it if user asks.
- promote to project: re-parent existing td tasks, no recreate.
- cancelled/archived -> propose delete/complete in Todoist.
- report under `## 🔄 Files changed`: counts created/updated/skipped.
