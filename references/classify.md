# classify
Every new input -> 1 of: project | light item | reminder | minute | update-existing. Step 0 always dedupe (references/dedupe.md).

## decide
| signal | class |
|---|---|
| multi-step, >1 owner, deps, target date, needs context/docs, user says "project" | project |
| single action, no deps | light item kind:task |
| time-bound nudge ("remind me", date only) | light item kind:rem (+agenda line) |
| vague thought, "to explore", "idea" | light item kind:idea, st:proposed |
| transcript/notes of meeting | minute -> Processor agent |
| matches existing open project/task | update-existing |
Unsure -> ask ONE short question, default light item.

## topic
Light items carry `topic:slug` (reuse existing topics: scan tracker topics first; never fork near-duplicate slugs).

## promote rule (threshold = config.promote_after, default 3)
`pa.py check --ctx C --text T --topic X` -> `PROMOTE_ASK yes` when 3 open light items already share topic X and a 4th arrives.
Then: ask user "convert topic X to project?" (show the 4 items).
On yes:
1 `pa.py new-project` (dedupe guard; if ARCHIVED_MATCH -> offer reactivate instead).
2 MOVE all topic-X light items to project actions.md: same ids, same fields, drop `topic`, keep src/td. Delete from tracker.md. Never copy.
3 Carry ALL known info: tracker agenda lines w/ ref -> project; related minutes/notes -> minutes/ or Context/ (confirmed:false if unverified); user statements -> index.md goal/state; new item = 4th task.
4 Fill index.md (goal, stake, due if known). Unknown -> blank.
5 Todoist (if on): update existing td tasks project mapping, no new tasks (references/todoist.md).
6 validate. Report moved ids.
On no: add item, no re-ask for same topic this session.
