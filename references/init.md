# init
Goal: empty|new folder -> valid vault. <=10 questions. No fixed paths.

## flow
1 Ask vault path (default suggestion: none; user decides). Expand ~. Create if missing (confirm).
2 Existing `.pro-assistant/config.md`? -> not new init: offer `sync-contexts`. Stop.
3 Ask contexts: names (e.g. companies + personal). Slug them.
4 Interview (short, skip known): name, role, tz, chat language (en|es|auto), msg tone, goals, key colleagues(name/role/ctx/channel). Per ctx: org name, role, goals.
5 Ask Todoist: on|off (default off). If on -> references/todoist.md checks.
6 Show summary of files to create. Confirm.
7 Run `pa.py --vault <V> init --contexts a,b [--todoist on|off]`.
8 Fill constitution.md + each _context.md from answers (EN, caveman, minimal edits). Mark `confirmed: true` only for user-stated facts.
9 Run `pa.py validate`. Report. Remind: tell agent vault path or run from inside vault so it resolves (cwd rule) or set PRO_ASSISTANT_HOME.

## rules
- script never overwrites existing files. idempotent.
- unanswered -> leave blank. never invent.
- no projects created at init.
