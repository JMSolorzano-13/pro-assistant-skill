# sync-contexts
Goal: align config contexts with folders. Touches ONLY config + context scaffolds (_context.md, tracker.md). Never tasks, projects, minutes.

## flow
1 `pa.py --vault <V> sync` -> known | new_on_disk | missing_on_disk.
2 Show diff. Ask per item:
  - new dir -> add as context? (rename suggestion if looks like renamed old ctx: ask, never auto-move)
  - missing dir -> drop from config? (`--drop name`; folder untouched) or restore.
3 Confirm. Apply: `sync --apply [--only a,b] [--drop x]`.
4 Updated profile data (org, goals, people, channels): edit `_context.md` / constitution.md minimal, show diff first.
5 `pa.py validate`.

## rules
- rename ctx = user renames folder, then sync (drop old + add new). Items inside keep ids. Never rewrite task text.
- new ctx with existing Projects/ -> validate must pass (index fm).
