---
type: config
schema: {{schema}}
skill_version: {{skill_version}}
contexts: [{{contexts}}]
todoist: {{todoist}}
promote_after: {{promote_after}}
view_port: {{view_port}}
refresh_min: {{refresh_min}}
---
# cfg
- vault = dir containing this .pro-assistant/. no abs paths stored.
- todoist: on|off. md = truth. todoist = mirror.
- promote_after: N open light items same topic -> item N+1 triggers promote-to-project ask.
- view_port: local read-only viewer port. refresh_min: viewer auto-refresh minutes.
