---
type: actions
ctx: acme-corp
project: PRJ-ALFA_MIGRATION
---
<!-- line: - [ ] text | id:T-xxxx | @owner | due:YYYY-MM-DD | pri:high|med|low | src:min-YYYY-MM-DD | st:proposed|confirmed|blocked|done|cancelled | td:(opt) -->
- [ ] Send migration plan to CTO | id:T-0001 | @juan | due:2026-10-16 | pri:high | st:doing
- [ ] Review schema diff | id:T-0002 | @ana | due:2026-10-25 | pri:med | st:confirmed | dep:T-0001
- [ ] Cutover rehearsal | id:T-0003 | @juan | due:2026-11-15 | pri:high | src:min-2026-10-15 | st:proposed | dep:T-0002
- [ ] Update runbook | id:T-0004 | @ana | pri:low | st:confirmed | dep:T-0002
