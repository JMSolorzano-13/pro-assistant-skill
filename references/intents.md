# intents
Map user phrase -> intent -> agent. Read only listed files. Write only w/ confirm. Resolve vault+ctx first (ask ctx if >1 and unclear).

| intent | ex | agent | read | write |
|---|---|---|---|---|
| capture | "remind me X", "track Y", "idea Z" | Classifier->Secretary | tracker, projects idx | tracker|actions (after check) |
| today | "what today" | Secretary | tracker, actions(due<=today, overdue) | - |
| week | "week pending" | Scrum | tracker, actions (7d) | - |
| upcoming | "next dates" | Secretary | tracker agenda, actions, idx.due | - |
| per-project | "pending in ctx" | PM | open Projects/*/actions | - |
| focus | "advise on Alfa" | Consultant | idx, actions, decisions, Context/ | - |
| risks | "risks Alfa|ctx" | Risk | idx(dep/blocks), actions, risks, decisions | risks.md |
| minute | "here's transcript" | Processor | minute, idx, actions | minutes/, actions (proposed) |
| complete | "done T-0001" | PM | actions|tracker | line st:done |
| reschedule | "move X to friday" | Scrum | actions|tracker | due |
| archive | "cancel project Beta" | PM | idx, actions | idx.status; open tasks -> cancel/move (ask) |
| reactivate | "resume Beta" | PM | idx | idx.status=active |
| promote | auto on 4th same-topic | PM | tracker | see classify.md |
| weekly-review | "friday review" | Scrum | all open | tracker.review (+ proposals); may write tracker w/o per-item confirm, show summary |
| view | "open diagram", "show timeline" | Secretary | - | - (runs `pa.py open`; read-only page) |
| adopt | "use my existing md" | Onboarding | existing files | see adopt.md |
| upgrade | "update vault" | Onboarding | config | see versioning.md |
| todoist-sync | "sync todoist" | Secretary | open tasks w/ due | td ids (see todoist.md) |
| init / sync-contexts | - | Onboarding | - | see init.md / sync-contexts.md |

## defaults
- today/week/upcoming: exclude archived projects, done, cancelled. include overdue first.
- week layout: Open(Mon-Tue) | Mid(Wed-Thu) | Close(Fri). flag no-owner/no-due.
- idle project: reviewed > 30d -> flag.
- workload: count open tasks per owner per week on request.
- every answer: humanizer.md (caller asks v1 -> output-contract.md).
- brief covers today|week|upcoming|pending|project|risks; `read` column = fallback when brief lacks data.
