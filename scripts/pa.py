#!/usr/bin/env python3
"""pro-assistant vault tool. stdlib only.
cmds: version | init | sync | validate | next-id | check | new-project | upgrade | model | view | open | checklist | ask | brief | apply | compose | prefs | lint-output | graph | dupes
exit: 0 ok | 1 validation errors | 2 refused (dup) | 3 ambiguous task | 4 task not found | 6 file changed | 7 outside vault | 8 task not open | 10 matches found"""
import argparse, contextlib, datetime, difflib, hashlib, io, json, os, re, socket, subprocess, sys, tempfile, time, webbrowser
import http.server, urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TPL = SKILL_DIR / "templates"
CFG = Path(".pro-assistant/config.md")
P_OPEN = {"active", "paused", "future"}
P_ARCH = {"obsolete", "cancelled", "completed"}
T_ST = {"proposed", "confirmed", "doing", "blocked", "done", "cancelled"}
PRI = {"high", "med", "low"}
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TASK = re.compile(r"^\s*- \[( |x)\] (.+)$")
STOP = {"the", "a", "an", "to", "of", "for", "and", "on", "in", "with", "my", "send", "do"}
IDX_REQ = ["type", "id", "name", "ctx", "status", "pri"]
SCHEMA = 2
DEFAULTS = {"todoist": "off", "promote_after": "3", "view_port": "8013", "refresh_min": "30"}
VERSION = (SKILL_DIR / "VERSION").read_text(encoding="utf-8").strip()
MIGRATIONS = {1: lambda v: None}  # 1->2 additive only (task dep:, st:doing, view cfg): no data change


def vtuple(s):
    try:
        return tuple(int(x) for x in str(s).split("."))
    except ValueError:
        return (0, 0, 0)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def fm(path):
    t = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n?", t, re.S)
    if not m:
        return None
    d = {}
    for line in m.group(1).splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if v.startswith("[") and v.endswith("]"):
            v = [x.strip() for x in v[1:-1].split(",") if x.strip()]
        d[k] = v
    return d


def toks(s):
    return [w for w in re.sub(r"[^a-z0-9 ]+", " ", s.lower()).split() if w not in STOP]


def sim(a, b):
    ta, tb = toks(a), toks(b)
    if not ta or not tb:
        return 0.0
    sa, sb = set(ta), set(tb)
    jac = len(sa & sb) / len(sa | sb)
    rat = difflib.SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio()
    return max(jac, rat)


def parse_task(line):
    m = TASK.match(line)
    if not m:
        return None
    parts = [p.strip() for p in m.group(2).split(" | ")]
    t = {"done": m.group(1) == "x", "text": parts[0], "owner": None}
    for p in parts[1:]:
        if p.startswith("@"):
            t["owner"] = p[1:]
        elif ":" in p:
            k, v = p.split(":", 1)
            t[k.strip()] = v.strip()
    return t


class Vault:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.cfg = fm(self.root / CFG) if (self.root / CFG).exists() else None

    @property
    def contexts(self):
        c = (self.cfg or {}).get("contexts", [])
        return c if isinstance(c, list) else [c]

    def projects(self, ctx):
        base = self.root / ctx / "Projects"
        out = []
        if base.is_dir():
            for d in sorted(base.iterdir()):
                if d.is_dir():
                    idx = d / "index.md"
                    out.append((d, fm(idx) if idx.exists() else None))
        return out

    def tasks(self, ctx):
        res = []
        files = [(self.root / ctx / "tracker.md", "tracker", None)]
        for d, f in self.projects(ctx):
            files.append((d / "actions.md", d.name, (f or {}).get("status")))
        for p, scope, ps in files:
            if not p.exists():
                continue
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                t = parse_task(line)
                if t:
                    res.append({"file": p, "line": i, "scope": scope, "pstatus": ps, "t": t})
        return res

    def all_md(self):
        return [p for p in self.root.rglob("*.md") if ".git" not in p.parts]


def rel(v, p):
    return str(p.relative_to(v.root))


def next_id(v):
    mx = 0
    for p in v.all_md():
        for m in re.finditer(r"\bid:T-(\d+)", p.read_text(encoding="utf-8")):
            mx = max(mx, int(m.group(1)))
    return "T-%04d" % (mx + 1)


def cmd_next_id(v, a):
    print(next_id(v))
    return 0


def match_report(v, ctx, text, topic=None):
    lines, found = [], False
    for d, f in v.projects(ctx):
        if not f:
            continue
        al = f.get("alias") or []
        names = [f.get("name", ""), d.name] + (al if isinstance(al, list) else [al])
        names = [n for n in names if n]
        s = max([sim(text, n) for n in names] or [0])
        if s >= 0.7 or slug(text) in [slug(n) for n in names]:
            tag = "PROJECT_MATCH" if f.get("status") in P_OPEN else "ARCHIVED_MATCH"
            lines.append("%s %s status:%s sim:%.2f" % (tag, d.name, f.get("status"), s))
            found = True
    for x in v.tasks(ctx):
        t = x["t"]
        if t["done"] or t.get("st") in ("done", "cancelled") or x["pstatus"] in P_ARCH:
            continue
        s = sim(text, t["text"])
        same = compare_tasks({"text": text}, t)
        if same and same[0] == "dup" and same[1] >= 0.85:
            s = max(s, same[1])
        if s >= 0.75:
            lines.append("TASK_MATCH %s in:%s sim:%.2f \"%s\"" % (t.get("id", "?"), x["scope"], s, t["text"]))
            found = True
    if topic:
        n = sum(1 for x in v.tasks(ctx) if x["scope"] == "tracker" and not x["t"]["done"]
                and x["t"].get("topic") == topic and x["t"].get("st") not in ("done", "cancelled"))
        thr = int((v.cfg or {}).get("promote_after", 3))
        lines.append("TOPIC_OPEN %s %d" % (topic, n))
        lines.append("PROMOTE_ASK %s" % ("yes" if n >= thr else "no"))
    return lines, found


def cmd_check(v, a):
    if a.ctx not in v.contexts:
        print("ERR unknown ctx", a.ctx)
        return 1
    lines, found = match_report(v, a.ctx, a.text, a.topic)
    print("\n".join(lines) if lines else "NONE")
    return 10 if found else 0


def cmd_validate(v, a):
    E, W = [], []
    ids_t, ids_p = {}, {}
    thr = int(v.cfg.get("promote_after", 3))
    todo_on = str(v.cfg.get("todoist", "off")).lower() == "on"
    vs, vv = int(v.cfg.get("schema", 0) or 0), v.cfg.get("skill_version", "0.0.0")
    if vs > SCHEMA:
        E.append("vault schema %d > skill schema %d: update skill" % (vs, SCHEMA))
    elif vs < SCHEMA:
        E.append("vault schema %d < skill schema %d: run upgrade" % (vs, SCHEMA))
    elif vtuple(vv) < vtuple(VERSION):
        W.append("vault skill_version %s < %s: run upgrade" % (vv, VERSION))
    elif vtuple(vv) > vtuple(VERSION):
        W.append("vault skill_version %s > skill %s: update skill" % (vv, VERSION))
    today = datetime.date.today()
    for top in sorted(v.root.iterdir()):
        if top.is_dir() and not top.name.startswith(".") and top.name not in v.contexts:
            W.append("dir not in config contexts: %s (run sync)" % top.name)
    for ctx in v.contexts:
        cdir = v.root / ctx
        if not cdir.is_dir():
            E.append("context dir missing: %s" % ctx)
            continue
        for need in ("_context.md", "tracker.md"):
            if not (cdir / need).exists():
                E.append("missing %s/%s" % (ctx, need))
        pids, names = {}, {}
        for d, f in v.projects(ctx):
            where = "%s/Projects/%s" % (ctx, d.name)
            if f is None:
                E.append("%s/index.md missing or no frontmatter" % where)
                continue
            for k in IDX_REQ:
                if k not in f:
                    E.append("%s index missing key: %s" % (where, k))
            if f.get("status") not in P_OPEN | P_ARCH:
                E.append("%s bad status: %s" % (where, f.get("status")))
            for k in ("start", "due", "reviewed"):
                if f.get(k) and not ISO.match(f[k]):
                    E.append("%s bad date %s: %s" % (where, k, f[k]))
            pid = f.get("id")
            if pid:
                if pid in ids_p:
                    E.append("dup project id %s (%s, %s)" % (pid, ids_p[pid], where))
                ids_p[pid] = where
                pids[pid] = f
            if f.get("status") in P_OPEN:
                al = f.get("alias") or []
                for n in [f.get("name", ""), d.name] + (al if isinstance(al, list) else [al]):
                    key = slug(n)
                    if key and key in names and names[key] != d.name:
                        E.append("dup active project name/alias '%s': %s vs %s" % (n, names[key], d.name))
                    names[key] = d.name
            if f.get("status") == "active" and f.get("reviewed") and ISO.match(f["reviewed"]):
                age = (today - datetime.date.fromisoformat(f["reviewed"])).days
                if age > 30:
                    W.append("%s stale review %dd" % (where, age))
            for k in ("actions.md", "risks.md", "decisions.md"):
                if not (d / k).exists():
                    W.append("%s missing %s" % (where, k))
        for pid, f in pids.items():
            for k in ("dep", "blocks"):
                refs = f.get(k, [])
                refs = refs if isinstance(refs, list) else [refs]
                for r in refs:
                    if r not in pids:
                        E.append("%s %s unknown ref %s" % (pid, k, r))
                    elif k == "blocks":
                        back = pids[r].get("dep", [])
                        if pid not in (back if isinstance(back, list) else [back]):
                            W.append("%s blocks %s but %s.dep lacks %s" % (pid, r, r, pid))
        seen_text, topic_n = {}, {}
        for x in v.tasks(ctx):
            t, loc = x["t"], "%s:%d" % (rel(v, x["file"]), x["line"])
            tid = t.get("id")
            if not tid:
                E.append("task no id @%s" % loc)
            elif not re.match(r"^T-\d{4,}$", tid):
                E.append("bad task id %s @%s" % (tid, loc))
            else:
                if tid in ids_t:
                    E.append("dup task id %s (%s, %s)" % (tid, ids_t[tid], loc))
                ids_t[tid] = loc
            st = t.get("st")
            if st not in T_ST:
                E.append("bad task st '%s' @%s" % (st, loc))
            if t.get("due") and not ISO.match(t["due"]):
                E.append("bad due '%s' @%s" % (t["due"], loc))
            if t.get("pri") and t["pri"] not in PRI:
                E.append("bad pri '%s' @%s" % (t["pri"], loc))
            if t["done"] != (st == "done") and st != "cancelled":
                W.append("checkbox/st mismatch @%s" % loc)
            openish = not t["done"] and st not in ("done", "cancelled")
            if openish:
                if not t["owner"]:
                    W.append("task no owner @%s" % loc)
                if not t.get("due") and t.get("kind") != "idea":
                    W.append("task no due @%s" % loc)
                if x["pstatus"] in P_ARCH:
                    W.append("open task in archived project @%s" % loc)
                for k, w in seen_text.items():
                    if sim(k, t["text"]) >= 0.9:
                        E.append("dup open task '%s' @%s vs %s" % (t["text"], loc, w))
                seen_text[t["text"]] = loc
                if x["scope"] == "tracker" and t.get("topic"):
                    topic_n[t["topic"]] = topic_n.get(t["topic"], 0) + 1
            if t.get("td") and not todo_on:
                W.append("td id present but todoist off @%s" % loc)
        opens = [dict(x["t"], due=x["t"].get("due")) for x in v.tasks(ctx) if x["t"].get("id") and not x["t"]["done"]
                 and x["t"].get("st") not in ("done", "cancelled") and x["pstatus"] not in P_ARCH]
        for d in find_dupes(opens):
            if d["kind"] == "dup" and d["same_owner_due"]:
                W.append("possible dup %s %s: run dupes" % (d["a"]["id"], d["b"]["id"]))
        for x in v.tasks(ctx):
            if x["t"].get("stage") and not x["t"].get("pkg"):
                W.append("stage without pkg %s" % x["t"].get("id"))
        for x in v.tasks(ctx):
            if not x["t"]["done"] and x["t"].get("st") not in ("done", "cancelled"):
                for code in OPAQUE.findall(x["t"]["text"]):
                    if not OPAQUE_OK.match(code):
                        W.append("opaque code %s @%s:%d: name the thing (schemas.md)" % (code, rel(v, x["file"]), x["line"]))
        tmap = {x["t"]["id"]: x["t"] for x in v.tasks(ctx) if x["t"].get("id")}
        graph = {tid: [d for d in t.get("dep", "").split(",") if d] for tid, t in tmap.items()}
        for tid, deps in graph.items():
            for d in deps:
                if d == tid:
                    E.append("task %s depends on itself" % tid)
                elif d not in tmap:
                    E.append("task %s dep unknown %s (same ctx only)" % (tid, d))
        color = {}

        def dfs(n, path):
            color[n] = 1
            for d in graph.get(n, []):
                if d == n or d not in graph:
                    continue
                if color.get(d) == 1:
                    E.append("task dep cycle: %s" % " > ".join(path + [n, d]))
                elif d not in color:
                    dfs(d, path + [n])
            color[n] = 2
        for n in graph:
            if n not in color:
                dfs(n, [])
        for k, n in topic_n.items():
            if n > thr:
                W.append("%s topic '%s' has %d open light items: promote to project?" % (ctx, k, n))
    tds = {}
    for ctx in v.contexts:
        for x in v.tasks(ctx):
            td = x["t"].get("td")
            if td:
                if td in tds:
                    E.append("dup todoist id %s (%s, %s)" % (td, tds[td], x["t"].get("id")))
                tds[td] = x["t"].get("id")
    for e in E:
        print("ERR", e)
    for w in W:
        print("WARN", w)
    print("validate: %d errors, %d warnings" % (len(E), len(W)))
    return 1 if E else 0


def render(_tpl, **kw):
    s = (TPL / _tpl).read_text(encoding="utf-8")
    for k, val in kw.items():
        s = s.replace("{{%s}}" % k, str(val))
    return s


def put(v, relpath, _tpl, created, **kw):
    p = v.root / relpath
    if p.exists():
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render(_tpl, **kw), encoding="utf-8")
    created.append(relpath)


def scaffold_ctx(v, ctx, created, today):
    put(v, "%s/_context.md" % ctx, "context.md", created, ctx=ctx, today=today)
    put(v, "%s/tracker.md" % ctx, "tracker.md", created, ctx=ctx, today=today)
    (v.root / ctx / "Projects").mkdir(parents=True, exist_ok=True)


def write_cfg(v, ctxs, created, skill_version=None, schema=None, **over):
    cfg = v.cfg or {}
    cur = {k: cfg.get(k, d) for k, d in DEFAULTS.items()}
    cur.update({k: x for k, x in over.items() if x is not None})
    sv = skill_version or cfg.get("skill_version", "0.0.0" if cfg else VERSION)
    sc = schema if schema is not None else cfg.get("schema", 0 if cfg else SCHEMA)
    p = v.root / CFG
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text(render("config.md", contexts=", ".join(ctxs), schema=sc, skill_version=sv, **cur),
                     encoding="utf-8")
        created.append(str(CFG))
        return
    # existing config may hold user keys and notes: change managed keys in place, nothing else
    text = p.read_text(encoding="utf-8")
    values = dict(cur, contexts="[%s]" % ", ".join(ctxs), schema=sc, skill_version=sv)
    for k, val in values.items():
        line = "%s: %s" % (k, val)
        text, n = re.subn(r"^%s:.*$" % re.escape(k), lambda _: line, text, count=1, flags=re.M)
        if not n:
            text = re.sub(r"\n---\n", "\n%s\n---\n" % line, text, count=1)
    p.write_text(text, encoding="utf-8")


def cmd_init(v, a):
    v.root.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    ctxs = [slug(c) for c in a.contexts.split(",") if slug(c)]
    if not ctxs:
        print("ERR need --contexts a,b")
        return 1
    created = []
    if v.cfg:
        ctxs = list(dict.fromkeys(v.contexts + ctxs))
        write_cfg(v, ctxs, created)
    else:
        write_cfg(v, ctxs, created, todoist=a.todoist, promote_after=a.promote_after)
    put(v, "constitution.md", "constitution.md", created, today=today)
    for c in ctxs:
        scaffold_ctx(v, c, created, today)
    print("created:" if created else "nothing new (idempotent)")
    for c in created:
        print(" ", c)
    return 0


def cmd_sync(v, a):
    on_disk = sorted(d.name for d in v.root.iterdir()
                     if d.is_dir() and not d.name.startswith(".") and d.name.lower() != "archive")
    cur = v.contexts
    new = [d for d in on_disk if d not in cur]
    gone = [c for c in cur if c not in on_disk]
    print("known:", ", ".join(cur) or "-")
    print("new_on_disk:", ", ".join(new) or "-")
    print("missing_on_disk:", ", ".join(gone) or "-")
    if not a.apply and not a.drop:
        return 0
    created = []
    ctxs = list(cur)
    only = a.only.split(",") if a.only else None
    if a.apply:
        for n in new:
            if only is None or n in only:
                ctxs.append(n)
    for d in (a.drop or "").split(","):
        if d and d in ctxs:
            ctxs.remove(d)
    today = datetime.date.today().isoformat()
    write_cfg(v, ctxs, created)
    for c in ctxs:
        if (v.root / c).is_dir():
            scaffold_ctx(v, c, created, today)
    print("applied. contexts:", ", ".join(ctxs))
    for c in created:
        print(" created", c)
    return 0


def cmd_new_project(v, a):
    ctx = a.ctx
    if ctx not in v.contexts:
        print("ERR unknown ctx", ctx)
        return 1
    lines, found = match_report(v, ctx, a.name)
    if found and not a.force:
        print("REFUSED similar/duplicate project. update or reactivate existing, or --force")
        print("\n".join(lines))
        return 2
    s = slug(a.name)
    d = v.root / ctx / "Projects" / s
    if d.exists():
        print("REFUSED dir exists:", rel(v, d))
        return 2
    today = datetime.date.today().isoformat()
    created = []
    kw = dict(id="PRJ-" + s.upper().replace("-", "_"), name=a.name, ctx=ctx, pri=a.pri,
              due=a.due or "", today=today)
    base = "%s/Projects/%s" % (ctx, s)
    for f in ("index.md", "actions.md", "risks.md", "decisions.md"):
        put(v, "%s/%s" % (base, f), f, created, **kw)
    (d / "minutes").mkdir(exist_ok=True)
    (d / "Context").mkdir(exist_ok=True)
    print("created:", base)
    return 0


def parse_risks(path):
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) < 9 or c[0] == "id" or set(c[0]) <= set("-: "):
            continue
        try:
            pr, im = int(c[2]), int(c[3])
        except ValueError:
            continue
        try:
            sev = int(c[4])
        except ValueError:
            sev = pr * im
        rows.append({"id": c[0], "risk": c[1], "P": pr, "I": im, "sev": sev, "mitigation": c[6],
                     "owner": c[7], "st": c[8]})
    return rows


def parse_sprints(path):
    """sprint plans as written in index.md: '- **<stream> sprint plan:**' then '  - **S23** (start..end): text'. dates stay null if absent."""
    rows, stream = [], None
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        head = re.match(r"^- \*\*(.+?) (?:sprint|publish) plan\b.*", line)
        if head:
            stream = head.group(1)
            continue
        m = re.match(r"^\s+- \*\*(S\d+)\*\*(?: \((\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})\))?: (.+)$", line)
        if not m:
            if not line.startswith((" ", "\t")):
                stream = None
            continue
        if stream:
            text = m.group(4).replace("*", "")
            rows.append({"stream": stream, "sprint": m.group(1), "start": m.group(2), "end": m.group(3), "text": text,
                         "refs": re.findall(r"\bT-\d+", text)})
    return rows


def org_name(path, default):
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, l in enumerate(lines):
            if l.strip() == "# org":
                for m in lines[i + 1:i + 4]:
                    if m.startswith("name:") and m[5:].strip():
                        return m[5:].strip()
    return default


def build_model(v):
    """read-only projection of vault md -> json for the viewer"""
    cfg = v.cfg or {}
    out = {"generated": datetime.datetime.now().isoformat(timespec="seconds"),
           "today": datetime.date.today().isoformat(), "schema": SCHEMA, "skill_version": VERSION,
           "refresh_min": int(cfg.get("refresh_min", DEFAULTS["refresh_min"])), "ctxs": []}
    for ctx in v.contexts:
        cdir = v.root / ctx
        if not cdir.is_dir():
            continue
        projects, edges, slug2id = [], set(), {}
        for d, f in v.projects(ctx):
            if not f:
                continue
            lst = lambda k: f.get(k, []) if isinstance(f.get(k, []), list) else ([f[k]] if f.get(k) else [])
            risks = parse_risks(d / "risks.md")
            openr = [r for r in risks if r["st"].lower() not in ("closed", "done", "mitigated")]
            pid = f.get("id", d.name)
            slug2id[d.name] = pid
            for x in lst("dep"):
                edges.add((x, pid))
            for x in lst("blocks"):
                edges.add((pid, x))
            projects.append({"id": pid, "slug": d.name, "name": f.get("name", d.name), "status": f.get("status"),
                             "pri": f.get("pri"), "start": f.get("start") or None, "due": f.get("due") or None,
                             "dep": lst("dep"), "blocks": lst("blocks"), "stake": lst("stake"),
                             "reviewed": f.get("reviewed") or None, "sprints": parse_sprints(d / "index.md"), "risk_max": max([r["sev"] for r in openr] or [0]),
                             "risks": openr[:5], "file": rel(v, d / "index.md")})
        tasks = []
        for x in v.tasks(ctx):
            t = x["t"]
            tasks.append({"id": t.get("id"), "text": t["text"], "owner": t["owner"], "due": t.get("due") or None,
                          "pri": t.get("pri"), "kind": t.get("kind"), "topic": t.get("topic"), "src": t.get("src"),
                          "st": t.get("st"), "td": t.get("td"), "done": t["done"], "pkg": t.get("pkg"), "stage": t.get("stage"), "rel": t.get("rel"),
                          "dep": [d for d in t.get("dep", "").split(",") if d],
                          "project": slug2id.get(x["scope"]) if x["scope"] != "tracker" else None,
                          "file": rel(v, x["file"]), "line": x["line"]})
        agenda = []
        tp = cdir / "tracker.md"
        if tp.exists():
            for l in tp.read_text(encoding="utf-8").splitlines():
                m = re.match(r"^(\d{4}-\d{2}-\d{2}) \| (.+?)(?: \| ref:(T-\d+))?\s*$", l)
                if m:
                    agenda.append({"date": m.group(1), "text": m.group(2), "ref": m.group(3)})
        out["ctxs"].append({"id": ctx, "name": org_name(cdir / "_context.md", ctx), "projects": projects,
                            "edges": sorted(edges), "tasks": tasks, "agenda": agenda})
    return out


def cmd_model(v, a):
    print(json.dumps(build_model(v), ensure_ascii=False, indent=1))
    return 0


def make_handler(root):
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                self._send(200, (TPL / "view.html").read_bytes(), "text/html; charset=utf-8")
            elif path == "/model.json":
                try:
                    body = json.dumps(build_model(Vault(root)), ensure_ascii=False).encode("utf-8")
                    self._send(200, body, "application/json; charset=utf-8")
                except Exception as e:  # read-only viewer: report, never crash
                    self._send(500, json.dumps({"error": str(e)}).encode(), "application/json")
            else:
                self._send(404, b"not found", "text/plain")
    return H


def port_of(v, a):
    return int(getattr(a, "port", None) or v.cfg.get("view_port", DEFAULTS["view_port"]))


def ours(port):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/model.json" % port, timeout=2) as r:
            return "ctxs" in json.loads(r.read().decode("utf-8"))
    except Exception:
        return False


def cmd_view(v, a):
    port = port_of(v, a)
    try:
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), make_handler(v.root))
    except OSError:
        print("ERR port %d busy%s" % (port, " (viewer already running: use open)" if ours(port) else ""))
        return 1
    url = "http://127.0.0.1:%d" % port
    print("view %s (read-only, ctrl-c stop)" % url, flush=True)
    if a.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def cmd_open(v, a):
    port = port_of(v, a)
    url = "http://127.0.0.1:%d" % port
    if not ours(port):
        if socket.socket().connect_ex(("127.0.0.1", port)) == 0:
            print("ERR port %d used by another app: use --port" % port)
            return 1
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--vault", str(v.root), "view",
                          "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        for _ in range(25):
            time.sleep(0.2)
            if ours(port):
                break
        else:
            print("ERR viewer did not start")
            return 1
    webbrowser.open(url)
    print("open", url)
    return 0


def cmd_version(v, a):
    print("skill %s schema %d" % (VERSION, SCHEMA))
    if v and v.cfg:
        print("vault skill_version %s schema %s" % (v.cfg.get("skill_version", "0.0.0"), v.cfg.get("schema", "0")))
    return 0


def cmd_upgrade(v, a):
    vs = int(v.cfg.get("schema", 0) or 0)
    if vs > SCHEMA:
        print("ERR vault schema %d > skill schema %d: update skill" % (vs, SCHEMA))
        return 1
    steps = []
    while vs < SCHEMA:
        fn = MIGRATIONS.get(vs)
        if fn is None and vs != 0:
            print("ERR no migration from schema %d" % vs)
            return 1
        if fn:
            fn(v)
            steps.append("schema %d->%d" % (vs, vs + 1))
        vs += 1
    old = v.cfg.get("skill_version", "0.0.0")
    if vtuple(old) > vtuple(VERSION):
        print("ERR vault %s > skill %s: update skill" % (old, VERSION))
        return 1
    write_cfg(v, v.contexts, [], skill_version=VERSION, schema=SCHEMA)
    print("upgraded %s -> %s %s" % (old, VERSION, " ".join(steps)))
    return 0


INTENTS = ("today", "week", "upcoming", "pending", "risks", "project", "unblock", "sprints", "on")
ST_HUMAN = {"proposed": "unconfirmed", "confirmed": "pending", "doing": "in progress", "blocked": "blocked"}
MONTHS = {"es": "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(),
          "en": "January February March April May June July August September October November December".split()}


def nat_date(iso, lang):
    if not iso:
        return "sin fecha" if lang == "es" else "no date"
    d = datetime.date.fromisoformat(iso)
    m = MONTHS[lang][d.month - 1]
    return "%d de %s de %d" % (d.day, m, d.year) if lang == "es" else "%s %d, %d" % (m, d.day, d.year)


def tsv(vals):
    return "\t".join("" if x is None else str(x).replace("\t", " ") for x in vals)


def bucket(due, today):
    if not due:
        return "nodate"
    d = datetime.date.fromisoformat(due)
    if d < today:
        return "overdue"
    if d == today:
        return "today"
    return "week" if d <= today + datetime.timedelta(days=7) else "later"


def clean(s):
    """internal refs inside free text (user-written or agent-written) must not reach the humanizer"""
    s = re.sub(r"\b(?:T-\d+|PRJ-[A-Z0-9_]+|[DR]-\d+)\b|[\w./~-]+\.md\b", "", str(s or ""))
    s = re.sub(r"\s+([,.;:)])", r"\1", re.sub(r"\(\s*\)|\[\s*\]", "", s))
    return re.sub(r"\s{2,}", " ", s).strip(" -,;:")


def sprint_text(text):
    """delivery text without task-id lists and their connectors"""
    s = re.sub(r"\s*\+?\s*\bT-\d+(?:\s*[/+,]\s*T-\d+)*(?:\s+[a-z]+)?\.?", "", text)
    return clean(s).rstrip(" .+")


def day(iso):
    """weekday computed here so the model never has to"""
    return "%s %s" % (iso, datetime.date.fromisoformat(iso).strftime("%a")) if iso else ""


def open_task(t):
    return not t["done"] and t["st"] not in ("done", "cancelled")


def task_graph(c):
    """in-memory graph from the model. nothing persisted, so nothing to sync. returns (open tasks, downstream ids)."""
    arch = {p["id"] for p in c["projects"] if p["status"] in P_ARCH}
    live = {t["id"]: t for t in c["tasks"] if t["id"] and open_task(t) and t["project"] not in arch}
    next_of = {i: [] for i in live}
    for i, t in live.items():
        for d in t["dep"]:
            if d in live:
                next_of[d].append(i)

    def reach(start):
        seen, todo = set(), list(next_of.get(start, []))
        while todo:
            n = todo.pop()
            if n not in seen:
                seen.add(n)
                todo += next_of.get(n, [])
        seen.discard(start)
        return seen
    return live, {i: reach(i) for i in live}


def brief_data(v, intent, ctx, project=None, as_of=None, expand=False, on=None):
    if intent == "on" and not iso_ok(on or ""):
        raise ValueError("on needs --date YYYY-MM-DD")
    expand = expand or intent == "on"
    today = datetime.date.fromisoformat(as_of) if as_of else datetime.date.today()
    c = next((x for x in build_model(v)["ctxs"] if x["id"] == ctx), None)
    if c is None:
        raise ValueError("unknown ctx %s" % ctx)
    focus = None
    if project:
        focus = next((p for p in c["projects"] if project in (p["slug"], p["id"], p["name"])), None)
        if focus is None:
            raise ValueError("unknown project %s" % project)
    live, down = task_graph(c)
    if intent == "unblock":
        chosen = sorted((t for t in live.values() if down[t["id"]] and (not focus or t["project"] == focus["id"])),
                        key=lambda t: (-len(down[t["id"]]), t["due"] or "9999"))[:8]
        rows = [(bucket(t["due"], today), t, 0, len(down[t["id"]])) for t in chosen]
    else:
        want = {"today": {"overdue", "today"}, "week": {"overdue", "today", "week"},
                "upcoming": {"today", "week", "later"}}.get(intent)
        order = {"overdue": 0, "today": 1, "week": 2, "later": 3, "nodate": 4}
        scope = [] if intent in ("risks", "sprints") else [t for t in live.values() if not focus or t["project"] == focus["id"]]
        groups = {}
        for t in scope:
            groups.setdefault(t.get("pkg") or t["id"], []).append(t)
        rows = []
        for members in groups.values():
            members.sort(key=lambda t: t["due"] or "9999")
            # pkg shows only its active stage unless expanded
            for t in (members if expand or len(members) == 1 else members[:1]):
                b = bucket(t["due"], today)
                if intent == "on" and t["due"] != on:
                    continue
                if not want or b in want:
                    rows.append((b, t, 0 if expand else len(members) - 1, len(down[t["id"]])))
        rows.sort(key=lambda r: (order[r[0]], r[1]["due"] or "9999"))
    agenda = []
    if intent == "on":
        agenda = [a for a in c["agenda"] if a["date"] == on]
    if intent in ("today", "week", "upcoming"):
        lim = {"today": 0, "week": 7}.get(intent)
        agenda = sorted((a for a in c["agenda"] if a["date"] >= today.isoformat()
                         and (lim is None or a["date"] <= (today + datetime.timedelta(days=lim)).isoformat())),
                        key=lambda a: a["date"])
    risks = []
    if intent in ("risks", "project"):
        risks = sorted(((p, r) for p in c["projects"] if p["status"] not in P_ARCH and (not focus or p is focus)
                        for r in p["risks"]), key=lambda x: -x[1]["sev"])
    sprints = []
    if intent == "sprints":
        by_id = {t["id"]: t for t in c["tasks"]}
        for p in c["projects"]:
            if p["status"] in P_ARCH or (focus and p is not focus):
                continue
            for s in p["sprints"]:
                refs = [by_id[r] for r in s["refs"] if r in by_id and by_id[r]["st"] != "cancelled"]
                still = [t for t in refs if open_task(t)]
                last = max(still, key=lambda t: t["due"] or "", default=None)
                state = "done" if refs and not still else "blocked" if any(t["st"] == "blocked" for t in still) else "pending" if still else ""
                sprints.append(dict(s, project=p["name"], owner=last["owner"] if last else None, state=state, open=[t["id"] for t in still]))
    return dict(today=today, c=c, focus=focus, rows=rows, agenda=agenda, risks=risks, down=down, sprints=sprints, live=live,
                pname={p["id"]: p["name"] for p in c["projects"]},
                text_of={t["id"]: t["text"] for t in c["tasks"]})


def build_brief(v, intent, ctx, project=None, audience="agent", as_of=None, expand=False, on=None):
    """compact projection. agent keeps ids. human has no id, code, path: safe input for the humanizer."""
    d = brief_data(v, intent, ctx, project, as_of, expand, on)
    c, human, pname, text_of = d["c"], audience == "human", d["pname"], d["text_of"]
    out = ["# %s %s %s" % (intent, c["name"] if human else ctx, d["today"].isoformat())]
    if on:
        out.append(tsv(["asked_date", day(on)]))
    if d["focus"]:
        out.append(tsv(["project", d["focus"]["name"], d["focus"]["status"], d["focus"]["due"]]))
    if d["rows"]:
        out.append(tsv(["when", "task", "owner", "date", "state", "project", "waits_on", "stages_left", "unblocks"] if human
                       else ["b", "id", "text", "owner", "due", "pri", "st", "prj", "dep", "stages_left", "unblocks"]))
    for b, t, more, unblocks in d["rows"]:
        if human:
            deps = "; ".join(clean(text_of[x]) for x in t["dep"] if x in d["live"])
            out.append(tsv([b, clean(t["text"]), t["owner"], day(t["due"]), ST_HUMAN.get(t["st"], ""),
                            pname.get(t["project"], ""), deps, more or "", unblocks or ""]))
        else:
            out.append(tsv([b, t["id"], t["text"], t["owner"], t["due"], t["pri"], t["st"], t["project"],
                            ",".join(t["dep"]), more or "", unblocks or ""]))
    if d["sprints"]:
        out.append("# sprints")
        out.append(tsv(["stream", "sprint", "start", "end", "delivery", "owner", "state"] + ([] if human else ["open"])))
        for s in d["sprints"]:
            row = [s["stream"], s["sprint"], s["start"], s["end"], sprint_text(s["text"]), s["owner"], s["state"]]
            out.append(tsv(row if human else row + [",".join(s["open"])]))
    if d["agenda"]:
        out.append("# agenda")
        out += [tsv([day(a["date"]), clean(a["text"])] if human else [a["date"], a["text"], a["ref"]]) for a in d["agenda"]]
    if d["risks"]:
        out.append("# risks")
        for p, r in d["risks"]:
            out.append(tsv([p["name"], clean(r["risk"]), r["sev"], clean(r["mitigation"]), r["owner"]] if human
                           else [p["name"], r["risk"], r["sev"], r["mitigation"], r["owner"], r["id"]]))
    return "\n".join(out)


def cmd_brief(v, a):
    try:
        print(build_brief(v, a.intent, a.ctx, a.project, a.audience, a.as_of, a.expand, a.date))
    except ValueError as e:
        print("ERR", e)
        return 1
    return 0


def find_tasks(v, ctx, tid=None, match=None):
    items = [x for x in v.tasks(ctx) if not (x["t"]["done"] or x["t"].get("st") in ("done", "cancelled"))] \
        if match else v.tasks(ctx)
    if tid:
        return [x for x in items if x["t"].get("id") == tid]
    scored = sorted(((sim(match, x["t"]["text"]), i) for i, x in enumerate(items)), reverse=True)
    return [items[i] for s, i in scored if s >= 0.5]


def seg_key(seg):
    s = seg.strip()
    if s.startswith("@"):
        return "@"
    return s.split(":", 1)[0].strip() if ":" in s else None


def seg_index(segs, key):
    return next((i for i, s in enumerate(segs) if i and seg_key(s) == key), -1)


def set_seg(segs, key, val, after=()):
    """replace in place keeping spacing; else insert after the first key found in `after`; else append."""
    i = seg_index(segs, key)
    if i >= 0:
        m = re.match(r"^(\s*%s\s*:\s*)(.*?)(\s*)$" % re.escape(key), segs[i])
        segs[i] = m.group(1) + val + m.group(3)
        return
    for k in after:
        j = seg_index(segs, k)
        if j >= 0:
            segs.insert(j + 1, "%s:%s" % (key, val))
            return
    segs.append("%s:%s" % (key, val))


def edit_line(line, op, a):
    segs = line.split(" | ")
    if op == "done":
        segs[0] = re.sub(r"^(\s*- \[) (\].*)$", r"\1x\2", segs[0])
        set_seg(segs, "st", "done")
    elif op == "cancel":
        set_seg(segs, "st", "cancelled")
    if op in ("due", "update") and a.due:
        set_seg(segs, "due", a.due, ("@", "id"))
    if op == "update" and a.pri:
        set_seg(segs, "pri", a.pri, ("due", "@", "id"))
    if op == "set":
        if a.pkg:
            set_seg(segs, "pkg", a.pkg)
        if a.stage:
            set_seg(segs, "stage", a.stage)
    return " | ".join(segs)


def read_raw(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def atomic_write(path, content):
    """temp+rename so a sync client never sees a partial file. keeps mode and line endings."""
    tmp = path.with_name(".%s.pa-tmp-%d" % (path.name, os.getpid()))
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    if path.exists():
        os.chmod(tmp, path.stat().st_mode & 0o777)
    os.replace(tmp, path)


def swap_line(raw, n, before, after):
    """replace 1-based line n only if it still equals `before`. other bytes untouched."""
    parts = re.split(r"(\r\n|\n)", raw)
    i = (n - 1) * 2
    if i >= len(parts) or parts[i] != before:
        return None
    parts[i] = after
    return "".join(parts)


def inside_vault(v, rel_path):
    """(path, None) or (None, reason). refuses absolute, parent and symlink escapes."""
    if "\0" in rel_path or os.path.isabs(rel_path) or ".." in Path(rel_path).parts:
        return None, "boundary"
    try:
        real = (v.root / rel_path).resolve(strict=True)
    except OSError:
        return None, "file_changed"
    if v.root.resolve() not in real.parents:
        return None, "boundary"
    return real, None


def validate_errors(v):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cmd_validate(Vault(v.root), None)
    return code, [l for l in buf.getvalue().splitlines() if l.startswith("ERR")]


def commit(v, edits):
    """all-or-nothing: snapshot, write, validate, restore on failure. edits = {path: new content}."""
    snapshots = {p: read_raw(p) for p in edits}
    try:
        for p, content in edits.items():
            atomic_write(p, content)
        code, errs = validate_errors(v)
    except Exception:
        for p, content in snapshots.items():
            atomic_write(p, content)
        raise
    if code:
        for p, content in snapshots.items():
            atomic_write(p, content)
    return errs if code else []


APPLY_EXIT = {"validation_failed": 1, "invalid_edit": 1, "ambiguous": 3, "not_found": 4, "file_changed": 6,
              "boundary": 7, "not_open": 8, "duplicate": 10}


def apply_result(a, kind=None, message="", record=None, preview=None, sync=None, matches=None):
    code = APPLY_EXIT[kind] if kind else 0
    if a.json:
        print(json.dumps({"ok": not kind, "kind": kind, "message": message, "applied": bool(a.yes and not kind),
                          "preview": preview, "record": record, "todoist": sync or [], "matches": matches or []},
                         ensure_ascii=False))
        return code
    if kind:
        print({"ambiguous": "AMBIGUOUS", "not_found": "NOT_FOUND", "duplicate": "MATCH", "file_changed": "FILE_CHANGED",
               "boundary": "BOUNDARY", "not_open": "NOT_OPEN", "validation_failed": "VALIDATE_ERRORS"}.get(kind, "ERR"), message)
        for m in matches or []:
            print(m)
        return code
    print("APPLIED" if a.yes else "PREVIEW", preview)
    for s in sync or []:
        print("TODOIST_SYNC", s)
    return 0


def cmd_apply(v, a):
    """dry-run unless --yes. preview text is built from the operation, never by a model. single vault writer."""
    es = a.lang == "es"
    if a.ctx not in v.contexts:
        return apply_result(a, "invalid_edit", "unknown ctx %s" % a.ctx)
    if a.due and not iso_ok(a.due):
        return apply_result(a, "invalid_edit", "bad date %s" % a.due)
    if a.op == "undo":
        return apply_undo(v, a)
    if a.op == "add":
        return apply_add(v, a, es)
    hits = find_tasks(v, a.ctx, a.task, a.match)
    if len(hits) != 1:
        rows = [tsv([x["t"].get("id"), x["t"]["text"], x["t"].get("due")]) for x in hits[:5]]
        return apply_result(a, "ambiguous" if hits else "not_found", matches=rows)
    x = hits[0]
    t, n = x["t"], x["line"]
    if a.op == "merge":
        return apply_merge(v, a, x, es)
    if a.op != "set" and (t["done"] or t.get("st") in ("done", "cancelled")):
        return apply_result(a, "not_open", "task is not open")
    if (a.op == "due" and not a.due) or (a.op == "update" and not (a.due or a.pri)) \
            or (a.op == "set" and not (a.pkg or a.stage)):
        return apply_result(a, "invalid_edit", "missing value for %s" % a.op)
    raw = read_raw(x["file"])
    before = re.split(r"\r\n|\n", raw)[n - 1]
    after = edit_line(before, a.op, a)
    msg = {"done": ('Marcar como hecha: "%s"' if es else 'Mark as done: "%s"') % t["text"],
           "cancel": ('Cancelar: "%s"' if es else 'Cancel: "%s"') % t["text"],
           "set": ('Agrupar "%s"' if es else 'Group "%s"') % t["text"],
           "update": ('Actualizar "%s"' if es else 'Update "%s"') % t["text"],
           "due": ('Mover "%s" de %s a %s' if es else 'Move "%s" from %s to %s')
           % (t["text"], nat_date(t.get("due"), a.lang), nat_date(a.due, a.lang)) if a.due else ""}[a.op]
    record = {"taskId": t.get("id"), "file": rel(v, x["file"]), "line": n, "before": before, "after": after, "kind": a.op}
    if not a.yes:
        return apply_result(a, preview=msg, record=record)
    errs = commit(v, {x["file"]: swap_line(raw, n, before, after)})
    if errs:
        return apply_result(a, "validation_failed", "restored", matches=errs)
    return apply_result(a, preview=msg, record=record, sync=[t["td"]] if t.get("td") else [])


def apply_undo(v, a):
    path, why = inside_vault(v, a.file or "")
    if why or not a.line or a.before is None or a.after is None:
        return apply_result(a, why or "invalid_edit", "bad undo target")
    raw = read_raw(path)
    next_raw = swap_line(raw, a.line, a.after, a.before)
    if next_raw is None:
        return apply_result(a, "file_changed", "line changed since the edit")
    record = {"file": a.file, "line": a.line, "before": a.after, "after": a.before, "kind": "undo"}
    if not a.yes:
        return apply_result(a, preview="undo", record=record)
    errs = commit(v, {path: next_raw})
    return apply_result(a, "validation_failed", "restored", matches=errs) if errs else apply_result(a, preview="undo", record=record)


def apply_add(v, a, es):
    if not a.text:
        return apply_result(a, "invalid_edit", "add needs --text")
    if a.project and a.project != slug(a.project):
        return apply_result(a, "boundary", "bad project")
    path = v.root / a.ctx / ("tracker.md" if not a.project else "Projects/%s/actions.md" % a.project)
    if not path.exists():
        return apply_result(a, "file_changed", "no target %s" % (a.project or "tracker"))
    lines, found = match_report(v, a.ctx, a.text)
    if found and not a.force:
        return apply_result(a, "duplicate", matches=lines)
    msg = ('Agregar "%s" (%s)' if es else 'Add "%s" (%s)') % (a.text, nat_date(a.due, a.lang))
    if not a.yes:
        return apply_result(a, preview=msg)
    tid = next_id(v)
    parts = [a.text, "id:" + tid] + (["@" + a.owner] if a.owner else []) + (["due:" + a.due] if a.due else []) \
        + (["pri:" + a.pri] if a.pri else []) + (["kind:%s" % a.kind] if not a.project and a.kind else []) \
        + (["topic:%s" % a.topic] if not a.project and a.topic else []) \
        + (["pkg:%s" % a.pkg] if a.pkg else []) + (["stage:%s" % a.stage] if a.stage else []) + ["st:confirmed"]
    raw = read_raw(path)
    errs = commit(v, {path: raw.rstrip("\r\n") + ("\r\n" if "\r\n" in raw else "\n") + "- [ ] " + " | ".join(parts)
                      + ("\r\n" if "\r\n" in raw else "\n")})
    if errs:
        return apply_result(a, "validation_failed", "restored", matches=errs)
    return apply_result(a, preview=msg, record={"taskId": tid, "file": rel(v, path), "kind": "add"})


def apply_merge(v, a, keep, es):
    """keep the task; drop --into-from: cancelled + dup_of, its deps move to keep, dependents re-pointed. lines stay."""
    if not a.drop or a.drop == keep["t"].get("id"):
        return apply_result(a, "invalid_edit", "merge needs a different --drop")
    gone = next((x for x in v.tasks(a.ctx) if x["t"].get("id") == a.drop), None)
    if gone is None:
        return apply_result(a, "not_found", "unknown --drop")
    kid, did = keep["t"]["id"], a.drop
    msg = ('Fusionar "%s" dentro de "%s"' if es else 'Merge "%s" into "%s"') % (gone["t"]["text"], keep["t"]["text"])
    new = {}

    def line_edit(path, n, fn):
        raw = new.get(path, read_raw(path))
        before = re.split(r"\r\n|\n", raw)[n - 1]
        new[path] = swap_line(raw, n, before, fn(before))

    def deps_of(t):
        return [x for x in t.get("dep", "").split(",") if x]

    def with_deps(line, deps):
        segs = line.split(" | ")
        if deps:
            set_seg(segs, "dep", ",".join(deps))
        elif seg_index(segs, "dep") >= 0:
            segs.pop(seg_index(segs, "dep"))
        return " | ".join(segs)
    merged = [x for x in dict.fromkeys(deps_of(keep["t"]) + deps_of(gone["t"])) if x not in (kid, did)]
    srcs = list(dict.fromkeys(x for t in (keep["t"], gone["t"]) for x in t.get("src", "").split(",") if x))

    def keep_line(l):
        segs = with_deps(l, merged).split(" | ")
        if srcs:
            set_seg(segs, "src", ",".join(srcs), ("note", "pri", "due", "@", "id"))
        return " | ".join(segs)
    line_edit(keep["file"], keep["line"], keep_line)

    def drop_line(l):
        segs = with_deps(l, []).split(" | ")
        set_seg(segs, "st", "cancelled")
        segs.append("dup_of:" + kid)
        return " | ".join(segs)
    line_edit(gone["file"], gone["line"], drop_line)
    moved = 0
    for x in v.tasks(a.ctx):
        i = x["t"].get("id")
        if i not in (kid, did) and did in deps_of(x["t"]):
            deps = [kid if d == did else d for d in deps_of(x["t"])]
            line_edit(x["file"], x["line"], lambda l, ds=list(dict.fromkeys(deps)): with_deps(l, ds))
            moved += 1
    tracker = v.root / a.ctx / "tracker.md"
    if tracker.exists():
        raw = new.get(tracker, read_raw(tracker))
        repointed, agenda = re.subn(r"(\| ref:)%s\b" % re.escape(did), lambda m: m.group(1) + kid, raw)
        if agenda:
            new[tracker] = repointed
    else:
        agenda = 0
    record = {"taskId": kid, "dropped": did, "dependents": moved, "agenda": agenda, "kind": "merge"}
    if not a.yes:
        return apply_result(a, preview=msg, record=record)
    errs = commit(v, new)
    if errs:
        return apply_result(a, "validation_failed", "restored", matches=errs)
    return apply_result(a, preview=msg, record=record, sync=[gone["t"]["td"]] if gone["t"].get("td") else [])


PREFS = Path(".pro-assistant/prefs.tsv")
PREF_KEYS = {"length": ("short", "normal"), "format": ("auto", "table", "list"), "diagrams": ("auto", "off"),
             "lang": ("auto", "es", "en"), "tone": ("direct", "formal", "warm")}
PREF_DEFAULT = {"length": "short", "format": "auto", "diagrams": "auto", "lang": "auto", "tone": "direct"}
DIAGRAM_MAX = 12
LEAKS = [("task id", r"\bT-\d+"), ("project id", r"\bPRJ-[A-Z0-9_]+"), ("decision/risk id", r"\b[DR]-\d+"),
         ("raw field", r"\b(?:id|st|td|dep|src|pri|due|ctx|sev|kind|topic):\S"), 
         ("file path", r"(?:^|[\s(`])[\w./~-]*\.(?:md|py|tsv|json|html)\b"), ("abs path", r"(?:^|\s)(?:~|/Users|/private)/\S+"),
         ("iso date", r"\b\d{4}-\d{2}-\d{2}\b"), ("tool name", r"\bpa\.py\b|\bvault\b|\bfrontmatter\b")]


OPAQUE = re.compile(r"(?<![\w-])(?:[A-Z]{1,3}\d{1,2}|DEC\d+|PIL\d+)(?![\w-])")
OPAQUE_OK = re.compile(r"^(?:S\d+|Q\d|W\d+)$")


def load_glossary(v, ctx):
    """<ctx>/_glossary.md. codes: forbidden labels -> name. terms: allowed words -> meaning for the subagent."""
    codes, terms, section = {}, {}, None
    p = v.root / ctx / "_glossary.md"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                section = line[2:].strip()
            elif " | " in line and not line.startswith("<!--"):
                c = [x.strip() for x in line.split(" | ")]
                if section == "codes":
                    codes[c[0]] = c[1]
                elif section == "terms":
                    terms[c[0]] = c[1]
    return codes, terms


def expand_codes(text, codes):
    if not codes:
        return text
    pat = r"(?<![\w-])(%s)(?![\w-])" % "|".join(sorted(map(re.escape, codes), key=len, reverse=True))
    return re.sub(pat, lambda m: codes[m.group(1)], text)


def read_prefs(v):
    out, p = dict(PREF_DEFAULT), v.root / PREFS
    if p.exists():
        for l in p.read_text(encoding="utf-8").splitlines():
            c = l.split("\t")
            if len(c) == 3 and c[1] in PREF_KEYS and c[2] in PREF_KEYS[c[1]]:
                out[c[1]] = c[2]
    return out


def cmd_prefs(v, a):
    """overlay in the vault, append-only: latest wins, undo drops last. allow-listed values only."""
    p = v.root / PREFS
    if a.action == "show":
        print("\n".join("%s=%s" % kv for kv in read_prefs(v).items()))
        return 0
    if a.action == "undo":
        ls = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
        if not ls:
            print("NOTHING_TO_UNDO")
            return 0
        print(("APPLIED undo %s" if a.yes else "PREVIEW undo %s") % ls[-1].split("\t", 1)[1].replace("\t", "="))
        if a.yes:
            atomic_write(p, "".join(x + "\n" for x in ls[:-1]))
        return 0
    if a.key not in PREF_KEYS or a.value not in PREF_KEYS[a.key]:
        print("ERR allowed:", " ".join("%s=%s" % (k, "|".join(x)) for k, x in PREF_KEYS.items()))
        return 1
    print(("APPLIED %s=%s" if a.yes else "PREVIEW %s=%s") % (a.key, a.value))
    if a.yes:
        cur = p.read_text(encoding="utf-8") if p.exists() else ""
        atomic_write(p, cur + tsv([datetime.date.today().isoformat(), a.key, a.value]) + "\n")
    return 0


def mermaid_label(s):
    return re.sub(r'["\[\]{}|<>]', " ", clean(s)).strip()


def build_diagram(v, ctx, project=None):
    """(mermaid or None, node count). node ids are positional, labels natural. project -> task graph, else project graph."""
    c = next((x for x in build_model(v)["ctxs"] if x["id"] == ctx), None)
    if c is None:
        return None, 0
    if project:
        focus = next((p for p in c["projects"] if project in (p["slug"], p["id"], p["name"])), None)
        items = {t["id"]: t["text"] for t in c["tasks"] if focus and t["project"] == focus["id"] and not t["done"]
                 and t["st"] not in ("done", "cancelled")}
        edges = [(d, t["id"]) for t in c["tasks"] if t["id"] in items for d in t["dep"] if d in items]
    else:
        items = {p["id"]: p["name"] for p in c["projects"] if p["status"] not in P_ARCH}
        edges = [tuple(e) for e in c["edges"] if e[0] in items and e[1] in items]
    used = sorted({n for e in edges for n in e})
    if not used:
        return None, 0
    if len(used) > DIAGRAM_MAX:
        return None, len(used)
    num = {n: "n%d" % i for i, n in enumerate(used, 1)}
    out = ["flowchart LR"] + ['  %s["%s"]' % (num[n], mermaid_label(items[n])) for n in used]
    out += ["  %s --> %s" % (num[x], num[y]) for x, y in sorted(edges)]
    return "\n".join(out), len(used)


def response_template(intent):
    t = (TPL / "responses.md").read_text(encoding="utf-8")
    base = re.search(r"^## all\n(.*?)(?=^## |\Z)", t, re.S | re.M)
    sec = re.search(r"^## %s\n(.*?)(?=^## |\Z)" % intent, t, re.S | re.M)
    return "".join(m.group(1) for m in (base, sec) if m).strip()


def owner_field(v, key):
    p = v.root / "constitution.md"
    m = re.search(r"^%s:[ \t]*(\S.*)$" % key, p.read_text(encoding="utf-8"), re.M) if p.exists() else None
    return m.group(1).strip() if m else ""


def build_compose(v, intent, ctx, project=None, as_of=None, on=None):
    """single input of the humanizer: rules + prefs + id-free data. holds no id, code or path."""
    prefs = read_prefs(v)
    if prefs["lang"] == "auto" and owner_field(v, "chat_lang") in ("es", "en"):
        prefs["lang"] = owner_field(v, "chat_lang")
    out = ["# template", response_template(intent), "# prefs", " ".join("%s=%s" % kv for kv in prefs.items()) + " you=" + (owner_field(v, "name") or "unknown").split()[0],
           "# data"]
    codes, terms = load_glossary(v, ctx)
    data = expand_codes(build_brief(v, intent, ctx, project, "human", as_of, on=on), codes)
    out.append(data)
    used = [(t, m) for t, m in terms.items() if re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(t), data)]
    if used:
        out += ["# glossary"] + ["%s = %s" % u for u in used]
    if codes:
        out.append("avoid: (?<![\\w-])(?:%s)(?![\\w-])" % "|".join(sorted(map(re.escape, codes))))
    if prefs["diagrams"] == "auto" and intent in ("project", "pending", "risks"):
        dg, n = build_diagram(v, ctx, project if intent == "project" else None)
        if dg:
            out += ["# diagram", dg]
        elif n:
            out += ["# diagram", "too large (%d items): use a table, offer the local visual page" % n]
    return "\n".join(out)


def cmd_compose(v, a):
    try:
        print(build_compose(v, a.intent, a.ctx, a.project, a.as_of))
    except ValueError as e:
        print("ERR", e)
        return 1
    return 0


def natural_dates(text):
    """(month, day) pairs written in natural ES/EN"""
    idx = {m.lower(): i + 1 for ms in MONTHS.values() for i, m in enumerate(ms)}
    al = "|".join(idx)
    found = {(idx[m.lower()], int(d)) for d, m in re.findall(r"\b(\d{1,2}) de (%s)\b" % al, text, re.I)}
    return found | {(idx[m.lower()], int(d)) for m, d in re.findall(r"\b(%s) (\d{1,2})\b" % al, text, re.I)}


def lint_output(text, payload=None):
    """deterministic gate on the final text. payload check covers dates and unconfirmed labels; not owners or counts."""
    errs = []
    for name, pat in LEAKS:
        hit = re.search(pat, text, re.M)
        if hit:
            errs.append("LEAK %s: %s" % (name, hit.group(0).strip()))
    if payload is not None:
        for terms in re.findall(r"^avoid: (.+)$", payload, re.M):
            hit = re.search(terms, text, re.I)
            if hit:
                errs.append("AVOID_TERM %s" % hit.group(0))
        if re.search(r"^# (?:today|on) ", payload, re.M):
            you = (re.findall(r"\byou=(\S+)", payload) or [""])[0].lower()
            for row in payload.splitlines():
                c = row.split("\t")
                if len(c) >= 5 and c[0] in ("overdue", "today", "week", "later", "nodate") and c[2]:
                    first = c[2].split()[0].lower()
                    if first != you and first not in text.lower():
                        errs.append("MISSING_OWNER %s" % c[2])
        said_dates = natural_dates(text)
        for c in (row.split("\t") for row in payload.splitlines()):
            if len(c) >= 4 and re.fullmatch(r"S\d+", c[1]) and iso_ok(c[3]) and re.search(r"\b%s\b" % c[1], text):
                end = datetime.date.fromisoformat(c[3])
                if (end.month, end.day) not in said_dates:
                    errs.append("MISSING_SPRINT_DATE %s" % c[1])
        # MM-DD also covers short dates users write inside free text
        known = {(int(m), int(d)) for m, d in re.findall(r"(?<!\d)(\d{2})-(\d{2})(?!\d)", payload)} | natural_dates(payload)
        for md in sorted(natural_dates(text) - known):
            errs.append("DATE_NOT_IN_DATA month=%d day=%d" % md)
        labeled = re.search(r"sin confirmar|por confirmar|unconfirmed|not confirmed", text, re.I)
        said = natural_dates(text)
        for row in payload.splitlines():
            c = row.split("\t")
            if len(c) < 5 or c[4] != "unconfirmed" or labeled:
                continue
            m = re.match(r"\d{4}-(\d{2})-(\d{2})", c[3])
            if c[1].lower() in text.lower() or (m and (int(m.group(1)), int(m.group(2))) in said):
                errs.append("MISSING_UNCONFIRMED_LABEL")
                break
    return errs


def cmd_lint_output(v, a):
    payload = Path(a.payload).read_text(encoding="utf-8") if a.payload else None
    errs = lint_output(sys.stdin.read(), payload)
    print("\n".join(errs) if errs else "OK")
    return 1 if errs else 0


ALIAS = {"st": "staging", "prod": "production", "docs": "doc", "tests": "test"}
NOISE = {"plan", "new", "blocked", "pending", "task"}


def iso_ok(s):
    if not ISO.match(s or ""):
        return False
    try:
        datetime.date.fromisoformat(s)
        return True
    except ValueError:
        return False


def task_shape(text):
    """(first word, stem set, digit tokens). digit tokens separate S23 from S24, phase 1 from phase 2."""
    words = re.sub(r"[^a-z0-9 ]+", " ", text.lower()).split()
    if not words:
        return "", set(), set()
    stem = {ALIAS.get(w, w) for w in words[1:]} - STOP - NOISE
    return words[0], stem, {w for w in stem if re.search(r"\d", w)}


def compare_tasks(a, b):
    """('dup'|'stage', jaccard) or None. dup = same verb same work. stage = other verb on same work."""
    va, sa, na = task_shape(a["text"])
    vb, sb, nb = task_shape(b["text"])
    if not sa or not sb or na != nb:
        return None
    j = len(sa & sb) / len(sa | sb)
    if j < 0.6:
        return None
    return ("dup" if va == vb else "stage"), j


def find_dupes(tasks):
    out = []
    for i, a in enumerate(tasks):
        for b in tasks[i + 1:]:
            if a.get("pkg") and a.get("pkg") == b.get("pkg"):
                continue
            hit = compare_tasks(a, b)
            if hit:
                same = a["owner"] == b["owner"] and a["due"] == b["due"]
                out.append(dict(kind=hit[0], score=round(hit[1], 2), same_owner_due=same, a=a, b=b))
    return sorted(out, key=lambda d: (d["kind"] != "dup", not d["same_owner_due"], -d["score"]))


def cmd_dupes(v, a):
    rows = []
    for c in build_model(v)["ctxs"]:
        if a.ctx and c["id"] != a.ctx:
            continue
        live, _ = task_graph(c)
        for d in find_dupes(list(live.values())):
            if d["kind"] == "stage" and not a.stages:
                continue
            rows.append(d)
            print(tsv([d["kind"], d["score"], "same" if d["same_owner_due"] else "diff", d["a"]["id"], d["b"]["id"],
                       d["a"]["text"], d["b"]["text"]]))
    if not rows:
        print("NONE")
    return 0


def cmd_graph(v, a):
    c = next((x for x in build_model(v)["ctxs"] if x["id"] == a.ctx), None)
    if c is None:
        print("ERR unknown ctx", a.ctx)
        return 1
    live, down = task_graph(c)
    if a.of:
        if a.of not in live:
            print("NOT_OPEN", a.of)
            return 4
        t = live[a.of]
        print(tsv(["task", a.of, t["text"], t["owner"], t["due"], t["st"]]))
        print(tsv(["waits_on"] + [x for x in t["dep"] if x in live]))
        print(tsv(["unblocks"] + sorted(down[a.of])))
        print(tsv(["rel"] + [x for x in (t.get("rel") or "").split(",") if x]))
        own = rel(v, v.root / t["file"])
        cited = sorted({rel(v, p) for p in (v.root / a.ctx).rglob("*.md")
                        if re.search(r"\b%s\b" % re.escape(a.of), p.read_text(encoding="utf-8")) and rel(v, p) != own})
        print(tsv(["cited_in"] + cited))
        return 0
    for t in sorted(live.values(), key=lambda t: -len(down[t["id"]]))[:a.top]:
        if down[t["id"]]:
            print(tsv([len(down[t["id"]]), t["id"], t["text"], t["owner"], t["due"], t["st"]]))
    return 0


DAYS = {"es": "lun mar mié jue vie sáb dom".split(), "en": "Mon Tue Wed Thu Fri Sat Sun".split()}
LABELS = {
    "es": dict(overdue="Vencida", today="Hoy", week="Esta semana", later="Más adelante", nodate="Sin fecha", task="Tarea",
               owner="Responsable", date="Fecha", state="Estado", project="Proyecto", when="Cuándo", none="sin responsable",
               nothing="No tienes nada registrado para esta consulta.", more="y %d más", next="Siguiente paso: %s",
               unlocks=" (libera %d)", agenda="Agenda", risks="Riesgos", risk="Riesgo", sev="Severidad", resp="Respuesta",
               high="alta", med="media", low="baja", stages=" (+%d etapas)", frees="Libera", waits="Espera a",
               lead_today="%d vencidas y %d para hoy.", target="Objetivo: %s.", unconfirmed="sin confirmar", pending="pendiente",
               progress="en curso", blocked="bloqueada", active="activo", paused="pausado", future="futuro"),
    "en": dict(overdue="Overdue", today="Today", week="This week", later="Later", nodate="No date", task="Task",
               owner="Owner", date="Date", state="State", project="Project", when="When", none="no owner",
               nothing="Nothing recorded for this question.", more="and %d more", next="Next step: %s",
               unlocks=" (frees %d)", agenda="Agenda", risks="Risks", risk="Risk", sev="Severity", resp="Response",
               high="high", med="medium", low="low", stages=" (+%d stages)", frees="Frees", waits="Waits on",
               lead_today="%d overdue and %d due today.", target="Target: %s.", unconfirmed="unconfirmed", pending="pending",
               progress="in progress", blocked="blocked", active="active", paused="paused", future="future")}


def nat_day(iso, lang):
    return "%s %s" % (DAYS[lang][datetime.date.fromisoformat(iso).weekday()], nat_date(iso, lang)) if iso else ""


def speak(text, lang):
    """free text for people: no internal refs, ISO dates spoken."""
    return re.sub(r"\b\d{4}-\d{2}-\d{2}\b", lambda m: nat_date(m.group(0), lang) if iso_ok(m.group(0)) else "", clean(text))


def table(head, rows):
    cell = lambda x: str(x).replace("|", "/")
    return "\n".join(["| %s |" % " | ".join(head), "|" + "---|" * len(head)] + ["| %s |" % " | ".join(cell(x) for x in r) for r in rows])


def render_answer(v, intent, ctx, project=None, lang="es", as_of=None, full=False, on=None):
    """deterministic answer: no model, so no invented facts. task text stays as stored."""
    prefs = read_prefs(v)
    d = brief_data(v, intent, ctx, project, as_of, on=on)
    L, rows, out = LABELS[lang], d["rows"], []
    state = {"proposed": L["unconfirmed"], "confirmed": L["pending"], "doing": L["progress"], "blocked": L["blocked"]}
    if d["focus"]:
        out.append("%s: %s.%s" % (d["focus"]["name"], L.get(d["focus"]["status"], d["focus"]["status"]),
                                  " " + L["target"] % nat_date(d["focus"]["due"], lang) if d["focus"]["due"] else ""))
    if intent == "today" and rows:
        out.append(L["lead_today"] % (sum(r[0] == "overdue" for r in rows), sum(r[0] == "today" for r in rows)))
    cap = 8 if prefs["length"] == "short" and not full else max(len(rows), len(d["risks"]), 1)
    shown = []
    for b, t, more, frees in rows[:cap]:
        text = speak(t["text"], lang) + (L["stages"] % more if more else "")
        shown.append([L[b], text, t["owner"] or L["none"], nat_day(t["due"], lang) or "-", state.get(t["st"], "-")]
                     + ([d["pname"].get(t["project"], "-")] if not d["focus"] else []) + ([frees] if intent == "unblock" else []))
    if shown:
        head = [L["when"], L["task"], L["owner"], L["date"], L["state"]] + ([L["project"]] if not d["focus"] else []) \
            + ([L["frees"]] if intent == "unblock" else [])
        if prefs["format"] == "list":
            out.append("\n".join("- " + " · ".join(str(x) for x in r if x != "-") for r in shown))
        else:
            out.append(table(head, shown))
        if len(rows) > cap:
            out.append(L["more"] % (len(rows) - cap) + ".")
    if d["sprints"]:
        out.append(table(["Plan", "Sprint", L["date"], L["task"], L["owner"], L["state"]],
                         [[s["stream"], s["sprint"], nat_date(s["end"], lang) if s["end"] else "-", speak(sprint_text(s["text"]), lang),
                           s["owner"] or L["none"], state.get(s["state"], s["state"]) or "-"] for s in d["sprints"]]))
    if d["agenda"]:
        out.append("%s:\n%s" % (L["agenda"], "\n".join("- %s: %s" % (nat_day(a["date"], lang), speak(a["text"], lang)) for a in d["agenda"])))
    if d["risks"]:
        word = lambda s: L["high"] if s >= 15 else L["med"] if s >= 8 else L["low"]
        out.append(table([L["risk"], L["sev"], L["resp"], L["owner"]] + ([L["project"]] if not d["focus"] else []),
                         [[speak(r["risk"], lang), word(r["sev"]), speak(r["mitigation"], lang), r["owner"] or L["none"]]
                          + ([p["name"]] if not d["focus"] else []) for p, r in d["risks"][:cap]]))
    if prefs["diagrams"] == "auto" and intent in ("project", "pending", "risks"):
        dg, _ = build_diagram(v, ctx, project if intent == "project" else None)
        if dg:
            out.append("```mermaid\n%s\n```" % dg)
    if not out or (intent in ("today", "week", "upcoming", "pending", "unblock", "sprints", "on") and not rows and not d["agenda"] and not d["sprints"]):
        return L["nothing"]
    cand = [r for r in rows if r[0] in ("overdue", "today")] or (rows if intent == "unblock" else [])
    if cand:
        top = max(cand, key=lambda r: r[3])
        out.append(L["next"] % speak(top[1]["text"], lang) + (L["unlocks"] % top[3] if top[3] else "") + ".")
    return expand_codes("\n\n".join(out), load_glossary(v, ctx)[0])


def cmd_ask(v, a):
    """single read entry: Python gathers facts, the subagent writes every answer. --raw = plain Python text for debug."""
    prefs = read_prefs(v)
    lang = a.lang or (prefs["lang"] if prefs["lang"] != "auto" else None) or \
        (owner_field(v, "chat_lang") if owner_field(v, "chat_lang") in ("es", "en") else "es")
    try:
        if a.raw:
            print(render_answer(v, a.intent, a.ctx, a.project, lang, a.as_of, True, a.date))
            return 0
        payload = build_compose(v, a.intent, a.ctx, a.project, a.as_of, a.date)
    except ValueError as e:
        print("ERR", e)
        return 1
    fd, path = tempfile.mkstemp(prefix="pa-payload-", suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(payload)
    print("PAYLOAD_FILE %s\n\nPregunta del usuario: %s\n\n%s" % (path, a.question or "(see # template)", payload))
    return 0


FOLLOW_UP = re.compile(r"^(monitor|track|follow|watch|risk gate)\b", re.I)
CHECK_SECTIONS = {"mine": "Mis acciones", "others": "Vencidos de otros: perseguir"}


def checklist_items(v, ctx, today, horizon, me):
    """action checklist: mine (overdue | due within horizon | no due) + others overdue.
    drops follow-ups (monitor/track/follow/risk gate) and doing items unless due today or overdue."""
    names = {d.name: (f or {}).get("name", d.name) for d, f in v.projects(ctx)}
    end = (datetime.date.fromisoformat(today) + datetime.timedelta(days=horizon)).isoformat()
    me = me.lower().split()
    out = []
    for x in v.tasks(ctx):
        t = x["t"]
        if t["done"] or t.get("st") not in ("confirmed", "doing", "blocked") or x["pstatus"] in P_ARCH:
            continue
        due = t.get("due") or ""
        late = bool(due) and due < today
        if not (due and due <= today) and (FOLLOW_UP.match(t["text"]) or t.get("st") == "doing"):
            continue
        owner = t["owner"] or ""
        mine = bool(me) and any(w in me for w in re.split(r"[+,\s]+", owner.lower()) if w)
        grp = "mine" if mine and (not due or due <= end) else "others" if late and not mine else None
        if not grp:
            continue
        fp = hashlib.sha1("|".join([t["text"], t.get("note", ""), due, owner, t.get("st", "")]).encode()).hexdigest()[:10]
        out.append({"id": t.get("id"), "t": t["text"], "note": t.get("note", ""), "own": owner, "due": due,
                    "pri": t.get("pri", ""), "st": t.get("st"), "grp": grp, "fp": fp,
                    "prj": names.get(x["scope"], "Light items") if x["scope"] != "tracker" else "Light items"})
    return out


def checklist_cache(v, ctx):
    return v.root / ".pro-assistant" / "cache" / ("checklist-%s.json" % ctx)


def cmd_checklist(v, a):
    """static page. Python picks items; the model only supplies display text (user lang) through --human."""
    if a.ctx not in v.contexts:
        print("ERR unknown ctx %s" % a.ctx)
        return 1
    today = a.as_of or datetime.date.today().isoformat()
    me = a.me or owner_field(v, "name").split(" ")[0]
    items = checklist_items(v, a.ctx, today, a.horizon, me)
    cpath = checklist_cache(v, a.ctx)
    cache = json.loads(cpath.read_text(encoding="utf-8")) if cpath.exists() else {}
    if a.human:
        new = json.loads(Path(a.human).read_text(encoding="utf-8"))
        fps = {i["id"]: i["fp"] for i in items}
        for tid, txt in new.items():
            if tid in fps and isinstance(txt, str) and txt.strip():
                cache[tid] = {"fp": fps[tid], "text": txt.strip()}
        cpath.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(cpath, json.dumps(cache, ensure_ascii=False, indent=1))
    stale = [i for i in items if cache.get(i["id"], {}).get("fp") != i["fp"]]
    if a.missing:
        print(tsv(["id", "project", "owner", "due", "st", "text", "note"]))
        for i in stale:
            print(tsv([i["id"], i["prj"], i["own"], i["due"], i["st"], i["t"], i["note"]]))
        return 0
    for i in items:
        c = cache.get(i["id"], {})
        i["h"] = c["text"] if c.get("fp") == i["fp"] else ""
    data = {"today": today, "ctx": a.ctx, "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "sections": CHECK_SECTIONS, "items": items}
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = (TPL / "checklist.html").read_text(encoding="utf-8").replace(
        '/*__DATA__*/{"today":"","ctx":"","generated":"","sections":{},"items":[]}', blob, 1)
    out = Path(a.out).expanduser() if a.out else v.root / ".pro-assistant" / ("checklist-%s.html" % a.ctx)
    out.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(out, html)
    n = {g: sum(1 for i in items if i["grp"] == g) for g in CHECK_SECTIONS}
    print("CHECKLIST %s items=%d mine=%d others=%d no_text=%d" % (out, len(items), n["mine"], n["others"], len(stale)))
    if a.open:
        webbrowser.open(out.as_uri())
    return 0


def main():
    ap = argparse.ArgumentParser(prog="pa.py")
    ap.add_argument("--vault")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("init")
    p.add_argument("--contexts", required=True)
    p.add_argument("--todoist", default="off", choices=["on", "off"])
    p.add_argument("--promote-after", default="3")
    p = sp.add_parser("sync")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--only")
    p.add_argument("--drop")
    sp.add_parser("validate")
    sp.add_parser("version")
    sp.add_parser("upgrade")
    sp.add_parser("model")
    p = sp.add_parser("view")
    p.add_argument("--port", type=int)
    p.add_argument("--open", action="store_true")
    p = sp.add_parser("open")
    p.add_argument("--port", type=int)
    sp.add_parser("next-id")
    p = sp.add_parser("check")
    p.add_argument("--ctx", required=True)
    p.add_argument("--text", required=True)
    p.add_argument("--topic")
    p = sp.add_parser("new-project")
    p.add_argument("--ctx", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--pri", default="med", choices=sorted(PRI))
    p.add_argument("--due")
    p.add_argument("--force", action="store_true")
    p = sp.add_parser("brief")
    p.add_argument("intent", choices=INTENTS)
    p.add_argument("--ctx", required=True)
    p.add_argument("--project")
    p.add_argument("--audience", default="agent", choices=["agent", "human"])
    p.add_argument("--as-of")
    p.add_argument("--expand", action="store_true")
    p.add_argument("--date")
    p = sp.add_parser("ask")
    p.add_argument("intent", choices=INTENTS)
    p.add_argument("--ctx", required=True)
    p.add_argument("--project")
    p.add_argument("--question")
    p.add_argument("--raw", action="store_true")
    p.add_argument("--date")
    p.add_argument("--lang", choices=["es", "en"])
    p.add_argument("--as-of")
    p = sp.add_parser("graph")
    p.add_argument("--ctx", required=True)
    p.add_argument("--of")
    p.add_argument("--top", type=int, default=10)
    p = sp.add_parser("dupes")
    p.add_argument("--ctx")
    p.add_argument("--stages", action="store_true")
    p = sp.add_parser("apply")
    p.add_argument("op", choices=["done", "cancel", "due", "update", "set", "add", "merge", "undo"])
    p.add_argument("--json", action="store_true")
    p.add_argument("--drop")
    p.add_argument("--pkg")
    p.add_argument("--stage")
    p.add_argument("--file")
    p.add_argument("--line", type=int)
    p.add_argument("--before")
    p.add_argument("--after")
    p.add_argument("--ctx", required=True)
    p.add_argument("--task")
    p.add_argument("--match")
    p.add_argument("--text")
    p.add_argument("--project")
    p.add_argument("--owner")
    p.add_argument("--due")
    p.add_argument("--pri", choices=sorted(PRI))
    p.add_argument("--kind", choices=["rem", "task", "idea"])
    p.add_argument("--topic")
    p.add_argument("--lang", default="es", choices=["es", "en"])
    p.add_argument("--force", action="store_true")
    p.add_argument("--yes", action="store_true")
    p = sp.add_parser("compose")
    p.add_argument("intent", choices=INTENTS)
    p.add_argument("--ctx", required=True)
    p.add_argument("--project")
    p.add_argument("--as-of")
    p = sp.add_parser("prefs")
    p.add_argument("action", choices=["show", "set", "undo"])
    p.add_argument("key", nargs="?")
    p.add_argument("value", nargs="?")
    p.add_argument("--yes", action="store_true")
    p = sp.add_parser("checklist")
    p.add_argument("--ctx", required=True)
    p.add_argument("--horizon", type=int, default=14)
    p.add_argument("--me")
    p.add_argument("--as-of")
    p.add_argument("--human")
    p.add_argument("--missing", action="store_true")
    p.add_argument("--out")
    p.add_argument("--open", action="store_true")
    p = sp.add_parser("lint-output")
    p.add_argument("--payload")
    a = ap.parse_args()
    if a.cmd == "version":
        return cmd_version(Vault(a.vault) if a.vault else None, a)
    if not a.vault:
        print("ERR --vault required")
        return 1
    v = Vault(a.vault)
    if a.cmd != "init" and not v.cfg:
        print("ERR vault not initialised (no %s). run init" % CFG)
        return 1
    fn = {"init": cmd_init, "sync": cmd_sync, "validate": cmd_validate, "next-id": cmd_next_id,
          "check": cmd_check, "new-project": cmd_new_project, "upgrade": cmd_upgrade, "model": cmd_model, "view": cmd_view,
          "open": cmd_open, "brief": cmd_brief, "apply": cmd_apply, "compose": cmd_compose,
          "prefs": cmd_prefs, "lint-output": cmd_lint_output, "ask": cmd_ask, "graph": cmd_graph, "dupes": cmd_dupes,
          "checklist": cmd_checklist}[a.cmd]
    return fn(v, a)


if __name__ == "__main__":
    sys.exit(main())
