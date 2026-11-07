# schemas
Audience = AI agents. Caveman: telegraphic, no articles/filler, key:value, tables, fixed abbrevs. Not human-readable by design. EN only.

## abbrevs
ctx=context(company|personal) | st=status | pri=priority | due=due date | src=source | dep=depends on | stake=stakeholders | alias=alt names | td=todoist id | rem=reminder | P=probability | I=impact | sev=severity | min=minute | PRJ=project id | T=task id | D=decision id | R=risk id

## dates
ISO only YYYY-MM-DD. Relative ("friday","tomorrow") -> resolve vs today + constitution.tz. Show resolved ISO. Ambiguous -> ask once, store `unknown`.

## vault
```
<V>/constitution.md              # owner, tz, tone, colleagues, rules (global)
<V>/.pro-assistant/config.md     # contexts, todoist, promote_after
<V>/<ctx>/_context.md            # org, goals, people, channels
<V>/<ctx>/tracker.md             # light items + agenda + review
<V>/<ctx>/Projects/<slug>/{index,actions,risks,decisions}.md, minutes/, Context/
```
Context dir names = slug (lowercase, hyphens).

## task line (single line, 1 task = 1 line)
`- [ ] text | id:T-0001 | @owner | due:2026-10-20 | pri:high | kind:task | topic:slug | src:min-2026-10-15 | st:confirmed | dep:T-0000,T-0002 | td:123`
- id: global vault-unique. get via `pa.py next-id`. never reuse, never renumber.
- text: EN, imperative, <=10 words.
- kind (light items): rem|task|idea. idea may lack due.
- topic: slug, light items only. drives promote rule.
- st: proposed|confirmed|doing|blocked|done|cancelled. `[x]` <=> st:done. doing = started.
- dep: optional, comma T-ids, same ctx only. no self, no cycles. only real blockers. moving task keeps dep.
- done -> keep line, set `[x]` + st:done. no delete.
- pri: high|med|low.
- pkg: optional slug. stage: optional verb, needs pkg. Same pkg = one piece of work; brief shows active stage (earliest due).
- rel: optional comma refs (T-|D-|R-|min-) = memory links, read by `graph --of`. dup_of: T-id, set by merge. Relations live here; graph is built in memory per call, no store.

## project index.md fm
type,id(PRJ-SLUG),name,alias[],ctx,status,pri,start,due,dep[],blocks[],stake[],reviewed
status: active|paused|future (open) | obsolete|cancelled|completed (archived: excluded from daily queries unless asked; stay in place, no move).
dep/blocks symmetric: A.blocks=[B] <=> B.dep=[A].

## context extra (Context/*.md)
fm: type=project_context, src, confirmed(true|false), validated(date). confirmed:false -> use only labeled "unconfirmed".

## risks.md
table. P1-5 x I1-5 = sev. low 1-6, med 8-12, high 15-25. Critical path from dep/blocks.

## decisions.md
`D-01 | date | decision | why | rejected | src`

## tracker.md
sections: light items | agenda (`date | text | ref:T-xxxx`) | review (last_weekly).

## minutes
minutes/min-YYYY-MM-DD[-n].md from templates/minute.md. Extracted commitments -> actions.md as st:proposed, src:min-<date>.
