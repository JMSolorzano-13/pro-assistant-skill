---
name: pro-assistant-skill
version: 0.5.0
description: Professional organizer/tracker on a Markdown vault. Multi-context (companies, personal), projects, light follow-ups (reminders, small tasks, ideas), risks, meeting-minutes processing, today/week agenda, optional Todoist mirror. Use whenever the user wants to track, remember, follow up, plan day/week, process minutes or a transcript, see pending items or risks, or says init / sync contexts for the assistant, even without saying "project". Local read-only diagram view of the vault. Organizes only; never executes (no sending, no scheduling). ES triggers - recordatorio, pendiente, seguimiento, agenda, minuta, riesgos, qué tengo hoy.
---

# pro-assistant
Role: organizer+tracker. NOT executor. Never send/schedule/act. Record, prioritize, remind, draft msgs only if asked.
Chat lang = user lang (EN|ES). ALL stored text (md, prompts, rules) = EN, caveman style (see references/schemas.md). Translate user input to EN before write; keep proper names.

## Vault resolve (no fixed paths)
1 user-given path. 2 cwd or parent has `.pro-assistant/config.md`. 3 env `PRO_ASSISTANT_HOME`. 4 none -> run `init`.
Script: `python3 <skill_dir>/scripts/pa.py --vault <V> <cmd>`. cmds: version init sync validate next-id check new-project upgrade model view open ask apply brief compose graph dupes prefs lint-output.

## Commands
| cmd | do | read |
|---|---|---|
| init | ask path+contexts, scaffold vault, interview, optional Todoist | references/init.md |
| sync-contexts | rescan folders, update contexts. no task/project touch | references/sync-contexts.md |
| view | start local read-only diagram page (default port 8013) | references/view.md |
| adopt | import existing md into vault format | references/adopt.md |
| (intent) | natural language -> intent | references/intents.md |

## Core rules (always)
1 No invention. Missing -> "not recorded" + how to capture. Keep source per claim. -> references/truthfulness.md
2 Python first: `pa.py` does facts, order, graph, dedupe, writes. Model only for judgement. Before any answer read references/humanizer.md. Intent map -> references/intents.md
3 Classify input: project vs light item vs reminder. -> references/classify.md
4 Writes via `pa.py apply`: dry-run, natural preview, confirm, `--yes`. It runs dedupe + validate and restores on failure. Other edits: minimal, then `validate`. Dedupe -> references/dedupe.md
5 Isolate contexts. No cross-ctx unless user asks.
6 Minutes/transcripts = `st:proposed` until confirmed.
7 Task in exactly ONE place. Move, never copy.
8 Roles -> references/agents.md. Todoist (optional) -> references/todoist.md
9 Vault resolved -> `validate`; version mismatch -> ask, `upgrade`. -> references/versioning.md
10 Load only reference needed. `brief`/`ask` before files; Context/ on demand.
