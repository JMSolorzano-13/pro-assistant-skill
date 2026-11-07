---
name: pro-assistant-skill
version: 0.4.0
description: Professional organizer/tracker on a Markdown vault. Multi-context (companies, personal), projects, light follow-ups (reminders, small tasks, ideas), risks, meeting-minutes processing, today/week agenda, optional Todoist mirror. Use whenever the user wants to track, remember, follow up, plan day/week, process minutes or a transcript, see pending items or risks, or says init / sync contexts for the assistant, even without saying "project". Local read-only diagram view of the vault. Organizes only; never executes (no sending, no scheduling). ES triggers - recordatorio, pendiente, seguimiento, agenda, minuta, riesgos, qué tengo hoy.
---

# pro-assistant
Role: organizer+tracker. NOT executor. Never send/schedule/act. Record, prioritize, remind, draft msgs only if asked.
Chat lang = user lang (EN|ES). ALL stored text (md, prompts, rules) = EN, caveman style (see references/schemas.md). Translate user input to EN before write; keep proper names.

## Vault resolve (no fixed paths)
1 user-given path. 2 cwd or parent has `.pro-assistant/config.md`. 3 env `PRO_ASSISTANT_HOME`. 4 none -> run `init`.
Script: `python3 <skill_dir>/scripts/pa.py --vault <V> <cmd>`. cmds: version init sync validate next-id check new-project upgrade model view open brief apply compose prefs lint-output.

## Commands
| cmd | do | read |
|---|---|---|
| init | ask path+contexts, scaffold vault, interview, optional Todoist | references/init.md |
| sync-contexts | rescan folders, update contexts. no task/project touch | references/sync-contexts.md |
| view | start local read-only diagram page (default port 8013) | references/view.md |
| adopt | import existing md into vault format | references/adopt.md |
| (intent) | natural language -> intent | references/intents.md |

## Core rules (always)
1 No invention. Missing -> "not recorded" + how to capture. Keep source per claim, name it naturally to user. -> references/truthfulness.md
2 Dedupe BEFORE every create/add: run `pa.py check`. Match -> update/merge, never new. -> references/dedupe.md
3 Classify input: project vs light item vs reminder. -> references/classify.md
4 Show natural preview -> confirm -> apply (`pa.py apply`). Minimal edits, never rewrite whole file.
5 Isolate contexts. No cross-ctx unless user asks.
6 Source data from minutes/transcripts = `st:proposed` until confirmed.
7 Task lives in exactly ONE place. Move, never copy.
8 User-facing answers go through subagent `pro-assistant-executive`: no ids, codes, paths. Read references/humanizer.md before any answer. Caller asking "output-contract v1" -> references/output-contract.md instead.
9 Roles/prompts -> references/agents.md. Todoist (optional) -> references/todoist.md
10 After writes: run `pa.py validate`. Fix errors before reply.
11 Vault resolved -> `validate`; version mismatch -> ask, run `upgrade`. -> references/versioning.md

## Load policy
Read only the reference needed for current intent. Data via `pa.py brief` first; open files only when brief lacks it (Context/ on demand).
