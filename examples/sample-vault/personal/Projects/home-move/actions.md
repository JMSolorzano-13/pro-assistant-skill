---
type: actions
ctx: personal
project: PRJ-HOME_MOVE
---
<!-- line: - [ ] text | id:T-xxxx | @owner | due:YYYY-MM-DD | pri:high|med|low | src:min-YYYY-MM-DD | st:proposed|confirmed|blocked|done|cancelled | td:(opt) -->
- [x] Sign lease | id:T-0013 | @juan | due:2026-10-05 | pri:high | st:done
- [ ] Book movers | id:T-0011 | @juan | due:2026-11-30 | pri:med | st:confirmed | dep:T-0013
- [ ] Notify bank of new address | id:T-0012 | @juan | pri:low | st:confirmed | dep:T-0011
