# pro-assistant-skill
EN: AI organizer/tracker on a local Markdown vault. Contexts (companies, personal), projects, light follow-ups, risks, minutes, agenda. Optional Todoist mirror. Organizes only; never executes. Vault files are written for AI agents (English, compressed).
ES: Organizador/seguimiento con IA sobre un vault Markdown local. Contextos (empresas, personal), proyectos, seguimientos ligeros, riesgos, minutas, agenda. Espejo opcional en Todoist. Solo organiza; no ejecuta. Los archivos del vault están escritos para agentes de IA (inglés, comprimido).

## Install / Instalar
Copy this folder into your agent skills dir (or install from skills.sh). / Copia esta carpeta al directorio de skills de tu agente (o instala desde skills.sh).

## Use / Uso
- `init` — create vault + contexts. / crea vault + contextos.
- `sync-contexts` — refresh contexts from folders. / actualiza contextos desde carpetas.
- `open` — read-only diagram at http://127.0.0.1:8013 (dependencies, timeline, projects). / diagrama solo lectura en http://127.0.0.1:8013 (dependencias, línea de tiempo, proyectos).
- Then talk naturally: "remind me…", "what's today", "process this transcript", "risks for Alfa". / Luego habla natural: "recuérdame…", "qué tengo hoy", "procesa esta minuta", "riesgos de Alfa".

## Requirements / Requisitos
Python 3.8+ (stdlib only). Todoist MCP optional. / Python 3.8+ (solo stdlib). MCP de Todoist opcional.

## Layout
`SKILL.md` router · `VERSION` + `CHANGELOG.md` (semver) · `references/` rules loaded on demand · `templates/` vault files · `agents/` user-facing subagent (Claude Code: symlink into `~/.claude/agents/`) · `scripts/pa.py` init, sync, validate, check, new-project, next-id, upgrade, model, view, open, brief, apply, compose, prefs, lint-output · `examples/sample-vault/`.
