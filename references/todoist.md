# todoist (optional, off by default)
Purpose: fast access in Todoist app. md = source of truth. Todoist = two-way mirror: vault -> Todoist push (rich text), Todoist -> vault read back as proposals (confirm before write). Skill never executes actions behind tasks.

## enable
config todoist:on only if user asked AND Todoist MCP tools present in session. Tools absent -> keep off, tell user, continue md-only. Never fail the flow because of Todoist.

## what to mirror (python `todoist plan`)
Open tasks with `due` or `td`, project not archived. Finished (done/cancelled) with `td` -> close in Todoist. Ideas w/o date skipped unless asked.

## task shape (written at sync time ONLY, user lang; never stored in vault md)
- title: user lang (ES default), clear, <=12 words: action + object + who/where. no ids, no codes, expand acronyms when short. e.g. "Iniciar migración de clientes Siigo Fiscal a IDP en producción".
- description: user lang, 3-6 short lines, plain text:
  1 Qué: what is done, concretely.
  2 Por qué: why it matters / what it unblocks (goal, decisions, blocks).
  3 Quién: owner + people involved (note).
  4 Fechas: due + key dates in note (start, meeting), natural dates.
  5 Depende de / Bloquea: open deps (owner, state) and blocked tasks, by name.
  6 Origen: meeting or decision it came from (src min-date -> "reunión del 10 de noviembre").
  Rules: no invention beyond line + note + goal + decisions + deps/blocks given by `plan`; skip a line with no data; no ids/paths inside prose.
- footer: added by python `---\nT-0001 · <ctx>`. Link key for dedupe. Never write it yourself.
- due: ISO date. priority: high->p1, med->p2, low->p4.
- project: Todoist project = md project name (light items -> ctx name). find existing first (exact name), create only if missing.
Cache: `.pro-assistant/cache/todoist-<ctx>.json` {T-id: td, fp, title, desc, sent_title, sent_desc, sent_due, sent_pri, seen[comment ids], closed}. UI cache in user lang (exception to EN-only), never facts. Text regenerated only when vault line fingerprint changes (cost control).

## run (one sync)
1 `pa.py --vault V todoist plan --ctx C [--project slug] --missing` -> JSON items needing text (new or vault line changed). Each has text, note, owner, due, pri, st, goal, decisions, deps, blocks, src.
2 Write `{"T-0001": {"title": "...", "desc": "..."}}` (rules above) to scratch file.
3 Read Todoist state for every OPEN item with `td` (from `plan` without --missing; finished ones optional): find-tasks by project (open only) + fetch-object for td ids missing there (completed) -> content, description, due (ISO), priority (p1-p4), checked, deleted; find-comments per task -> [{id, content, at}]. Write `{"<td>": {...,"comments":[...]}}`. Task not found -> omit (python flags deleted).
4 `pa.py todoist diff --ctx C --texts <t.json> --remote <r.json>` -> {counts, push[], feedback[], need_text[]}. need_text non-empty -> back to 2.
5 Show user ONE preview in natural language: push (create/update/close counts + titles) and feedback proposals grouped by task. Confirm.
6 Push confirmed ops via MCP: create -> add-tasks (content=title, description, dueString, priority, project); update -> update-tasks (content/description/priority) + reschedule-tasks for due; close -> complete-tasks; reopen (we closed it, vault open again) -> uncomplete-tasks, then same fields as update. Collect results `[{"id","op","td", title?, description?, due?, priority?}]` (fields actually sent; td from create result).
7 `pa.py todoist commit --ctx C --result <res.json> --remote <r.json> [--ack T-a,T-b]` -> writes td ids to md (validate+restore), sets baseline. `--ack` = feedback processed for those ids (their comments marked seen, Todoist edits become baseline).
8 Report under `## 🔄 Files changed`: created/updated/closed + feedback applied/skipped.

## read back (feedback kinds -> vault, confirm each batch)
- completed -> `apply done`.
- comment / desc_edit / title_edit -> user words: interpret like checklist answers (references/checklist.md "answers back"): note update (translate EN, `src:todoist-<date>`), due, owner, blocked, new task (`add`, dedupe), cancel. Unclear -> ask.
- due_change -> `apply due` to Todoist date. pri_change -> `apply update --pri`.
- deleted -> ask: cancel in vault, recreate in Todoist, or unlink (drop td). Never auto-cancel.
After applying -> step 7 with `--ack` for those ids; next sync rewrites their text from the updated vault line. Skipped feedback -> no ack (shows again next sync; user edits never overwritten until acked).

## dedupe (no dup in Todoist)
1 md line has `td:<id>` -> update that task, never create.
2 no td: search Todoist for `T-xxxx` in description (and exact title+due). found -> result entry op "create" with that td (python writes td, no new task).
3 not found -> create, commit writes `td:<id>`.
4 `validate` errors on dup td ids.

## rules
- promote to project: re-parent existing td tasks, no recreate.
- first sync on legacy tasks (description = id only): treated as ours; title/description rewritten; due/priority: vault wins.
