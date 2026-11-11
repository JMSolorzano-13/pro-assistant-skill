# intents
Resolve vault+ctx first (ask ctx if >1 and unclear). Route by who can answer. Read/write flow -> humanizer.md.

## facts from python (`ask <intent>`), answer from subagent
today | week | upcoming | pending | risks | project (--project) | unblock ("what frees most work") | sprints (delivery dates by sprint).
on (--date ISO: tasks of one date). Always pass `--question "<user words>"`.

## backend role + subagent answer
| intent | ex | role | extra read |
|---|---|---|---|
| focus | "advise on Alfa" | Consultant | decisions, Context/ |
| risk analysis | "assess risks Alfa" | Risk | risks, decisions; writes risks.md |
| minute | "here's transcript" | Processor | minute; writes minutes/, actions (proposed) |
| weekly-review | "friday review" | Scrum | `ask week`, `dupes`; writes tracker.review; summary shown |

## writes (`apply`, dry-run first)
capture (classify.md -> add) | complete -> done | reschedule -> due | cancel | group stages -> set --pkg --stage | duplicates -> `dupes` then merge.
Project: archive/reactivate/promote -> PM role, edit idx (classify.md, dedupe.md).

## other
view -> `open` (view.md) | checklist / action page -> checklist.md | adopt (adopt.md) | upgrade (versioning.md) | todoist-sync -> `todoist plan|diff|commit` (todoist.md) | init/sync-contexts (init.md, sync-contexts.md).

## defaults
Excluded unless asked: archived projects, done, cancelled. Week layout on request: Open(Mon-Tue) | Mid(Wed-Thu) | Close(Fri). Idle project (reviewed >30d) -> flag.
