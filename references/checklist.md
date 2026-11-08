# checklist
Static action page per ctx: user answers each item, edits status/date, copies changes back to chat. Source = vault md. Page never writes vault.
Triggers (ES): "checklist", "documento de pendientes", "página de seguimiento", "acciones pendientes", "dame la lista para contestar".

## pick (python, `checklist_items`)
- open only: st confirmed|doing|blocked, project not archived.
- mine = owner has user first name (constitution `name`, or `--me`). mine + (overdue | due <= today+horizon(14) | no due) -> "Mis acciones".
- others overdue -> "Vencidos de otros: perseguir". others not overdue -> out.
- follow-up text (Monitor|Track|Follow|Watch|Risk gate) and st:doing -> out unless due today or overdue.
- item shows project name (index.md `name`; tracker -> "Light items"). page groups by section or project, filters by project.

## run
1 `pa.py --vault V checklist --ctx C --missing` -> TSV items w/o fresh display text (new, or text/note/due/owner/st changed).
2 rows -> write user-lang text per id, JSON `{"T-0001": "..."}` in scratch dir. Rules: who does what + key context (deadline, why blocked, meeting time); natural dates; expand acronyms; no ids, codes, paths; no invention beyond line+note.
3 `pa.py --vault V checklist --ctx C --human <json> --open` -> merges cache, writes `.pro-assistant/checklist-<ctx>.html`, opens browser. Output `CHECKLIST <path> items= mine= others= no_text=`; no_text>0 -> repeat 1-3.
4 Tell user: path + counts. No other summary.
Flags: `--horizon N`, `--as-of ISO`, `--me NAME`, `--out PATH`.

## answers back
User pastes "Copiar cambios" block: `- T-xxxx | project | text | st:a->b | due:a->b | resp: ...`.
- Paste = user words: apply what it asks. done/cancel/due/merge via `apply`; notes + text fixes = minimal edit, translate to EN, `src:user-<date>`, then `validate`.
- "duplicada"/"se repite" -> `merge` (keep older id). "eliminar"/"no existe" -> `cancel` + note reason (never delete line).
- "recordar <day>" -> `due` to that date. new work stated -> `add` (dedupe runs).
- Todoist on -> propose mirror of the `TODOIST_SYNC` ids (todoist.md).
- Then rerun steps 1-3 so page shows new state. Answers in browser reset per item when vault line changes.

## cache
`.pro-assistant/cache/checklist-<ctx>.json` {id: {fp, text}}. UI display cache in user lang: exception to EN-only rule, never read as facts, safe to delete (rebuilt via steps 1-3).
