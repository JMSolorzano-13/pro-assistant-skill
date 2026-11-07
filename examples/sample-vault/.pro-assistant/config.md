---
type: config
schema: 2
skill_version: 0.3.0
contexts: [acme-corp, personal]
todoist: off
promote_after: 3
view_port: 8013
refresh_min: 30
---
# cfg
- vault = dir containing this .pro-assistant/. no abs paths stored.
- todoist: on|off. md = truth. todoist = mirror.
- promote_after: N open light items same topic -> item N+1 triggers promote-to-project ask.
- view_port: local read-only viewer port. refresh_min: viewer auto-refresh minutes.
