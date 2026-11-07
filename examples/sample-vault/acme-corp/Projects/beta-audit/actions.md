---
type: actions
ctx: acme-corp
project: PRJ-BETA_AUDIT
---
<!-- line: - [ ] text | id:T-xxxx | @owner | due:YYYY-MM-DD | pri:high|med|low | src:min-YYYY-MM-DD | st:proposed|confirmed|blocked|done|cancelled | td:(opt) -->
- [ ] Collect audit evidence | id:T-0006 | @juan | due:2026-11-05 | pri:med | st:blocked
- [ ] Write audit report | id:T-0007 | @juan | due:2026-11-20 | pri:med | st:confirmed | dep:T-0006
