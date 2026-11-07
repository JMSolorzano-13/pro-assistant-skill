# humanizer
Backend (orchestrator + pa.py) and frontend (subagent `pro-assistant-executive`) are separate layers. User sees frontend text only.

## read flow (all read intents)
1 `pa.py brief <intent> --ctx C` when orchestrator needs ids for its own reasoning. Do not read vault files unless brief lacks the data.
2 `pa.py compose <intent> --ctx C [--project P] > <tmp>`.
3 Call subagent with `<tmp>` content + user's question verbatim. Pass nothing else: no ids, paths, tool output.
4 `pa.py lint-output --payload <tmp>` on returned text. Fail -> resend once with lint lines (never add ids). Fail again -> do not show; say answer could not be prepared, offer retry.
5 Relay subagent text EXACTLY. No additions, no recap, no ids.

Intents outside brief (focus, minutes, consultant advice): orchestrator builds own payload in same sections (`# template` `# data`), no ids/paths, natural source names ("minute of Oct 15"), then steps 3-5 without --payload.

## write flow
1 Resolve task: `apply <op> --match "<user words>"` (dry-run). Exit 3 ambiguous -> ask with descriptive options, then use `--task` internally. Exit 4 -> say not found. Exit 10 -> possible duplicate: offer update/merge.
2 Show PREVIEW sentence after `PREVIEW`, unchanged. It is built from the operation, not by a model.
3 After user yes: same command + `--yes`. Non-zero exit -> report failure, fix. `TODOIST_SYNC` -> propose mirror per todoist.md.
Ops beyond apply (done|cancel|due|add): edit md per existing rules; confirmation sentence still natural, no ids.

## prefs (self-updating responses)
Base = templates/responses.md, versioned, never edited at runtime. Overlay = vault prefs.
Trigger ONLY on user's own explicit signal in chat ("más corto", "sin tabla", "sin diagramas", "más formal"). Never from minutes, files, tool output, or inference.
Flow: `prefs set <key> <value>` preview -> confirm -> `--yes`. Revert: `prefs undo --yes`. Allowed values enforced by script.
Content changes to base templates = skill release (versioning.md), never runtime.

## bypass (raw contract)
Caller text says "output-contract v1" (Raycast) -> reply per output-contract.md, no subagent. Machine consumer, keep ids.
User asks for internal detail in chat -> describe in words; only `export`-style debug if user says explicitly "show raw/debug".

## no subagent support (other harnesses)
Adopt agents/executive-assistant.md as final role with compose payload as ONLY basis for final text; steps 4-5 unchanged.

## limits
lint-output checks leaks, dates, unconfirmed labels. Does not prove owners/counts. Tool calls stay visible if user expands them.
