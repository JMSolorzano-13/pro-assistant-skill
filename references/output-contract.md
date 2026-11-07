# output-contract v1
Machine channel ONLY: caller explicitly asks "output-contract v1" (Raycast). Human chat -> references/humanizer.md.
Headers fixed EN (machine-parseable). Body in user chat lang. Sections only if applicable, this order.

```
contract: v1
## 📅 Agenda
## 🚨 Risks
## 💬 Quick messages
## 📆 Calendar actions
## 🔄 Files changed
## ❓ Pending confirmation
## 📎 Sources
```
- line 1 exactly `contract: v1`.
- Agenda: bucket overdue|today|week|upcoming. row: `ISO | text | T-id | owner | st`.
- Risks: sev, root cause, critical-path impact, mitigation.
- Quick messages: `to: <name> (<channel>)` + copy-ready text. draft only; user sends.
- Calendar actions: who | topic | proposed ISO. proposal only; user schedules.
- Files changed: path + change. applied only after confirm; before confirm title it as proposed in Pending.
- Pending confirmation: proposed/unknown data, dup matches, promote ask.
- Sources: files used (relative paths).
- Close with human-executable actions (inside the sections above).
- Todoist section not in contract; mention sync result under Files changed.
