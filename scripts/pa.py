#!/usr/bin/env python3
"""pro-assistant vault tool. stdlib only.
cmds: version | init | sync | validate | next-id | check | new-project | upgrade | model | view | open | brief | apply | compose | prefs | lint-output
exit: 0 ok | 1 validation errors | 2 refused (dup) | 3 ambiguous task | 4 task not found | 10 check found matches"""
import argparse, contextlib, datetime, difflib, io, json, os, re, socket, subprocess, sys, time, webbrowser
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
    existed = p.exists()
    p.write_text(render("config.md", contexts=", ".join(ctxs), schema=sc, skill_version=sv, **cur),
                 encoding="utf-8")
    if not existed:
        created.append(str(CFG))


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
                             "reviewed": f.get("reviewed") or None, "risk_max": max([r["sev"] for r in openr] or [0]),
                             "risks": openr[:5], "file": rel(v, d / "index.md")})
        tasks = []
        for x in v.tasks(ctx):
            t = x["t"]
            tasks.append({"id": t.get("id"), "text": t["text"], "owner": t["owner"], "due": t.get("due") or None,
                          "pri": t.get("pri"), "kind": t.get("kind"), "topic": t.get("topic"), "src": t.get("src"),
                          "st": t.get("st"), "td": t.get("td"), "done": t["done"],
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


INTENTS = ("today", "week", "upcoming", "pending", "risks", "project")
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


def day(iso):
    """weekday computed here so the model never has to"""
    return "%s %s" % (iso, datetime.date.fromisoformat(iso).strftime("%a")) if iso else ""


def build_brief(v, intent, ctx, project=None, audience="agent", as_of=None):
    """compact projection. agent keeps ids. human has no id, code, path: safe input for the humanizer."""
    today = datetime.date.fromisoformat(as_of) if as_of else datetime.date.today()
    c = next((x for x in build_model(v)["ctxs"] if x["id"] == ctx), None)
    if c is None:
        raise ValueError("unknown ctx %s" % ctx)
    human = audience == "human"
    pname = {p["id"]: p["name"] for p in c["projects"]}
    arch = {p["id"] for p in c["projects"] if p["status"] in P_ARCH}
    focus = None
    if project:
        focus = next((p for p in c["projects"] if project in (p["slug"], p["id"], p["name"])), None)
        if focus is None:
            raise ValueError("unknown project %s" % project)
    text_of = {t["id"]: t["text"] for t in c["tasks"]}
    head = ["# %s %s %s" % (intent, c["name"] if human else ctx, today.isoformat())]
    want = {"today": {"overdue", "today"}, "week": {"overdue", "today", "week"},
            "upcoming": {"today", "week", "later"}}.get(intent)
    rows, order = [], {"overdue": 0, "today": 1, "week": 2, "later": 3, "nodate": 4}
    if intent != "risks":
        for t in c["tasks"]:
            if t["done"] or t["st"] in ("done", "cancelled") or t["project"] in arch:
                continue
            if focus and t["project"] != focus["id"]:
                continue
            b = bucket(t["due"], today)
            if want and b not in want:
                continue
            rows.append((order[b], t["due"] or "9999", b, t))
    rows.sort(key=lambda r: r[:2])
    out = list(head)
    if rows:
        if human:
            out.append(tsv(["when", "task", "owner", "date", "state", "project", "waits_on"]))
        else:
            out.append(tsv(["b", "id", "text", "owner", "due", "pri", "st", "prj", "dep"]))
    for _, _, b, t in rows:
        if human:
            deps = "; ".join(clean(text_of.get(d, "")) for d in t["dep"] if d in text_of)
            out.append(tsv([b, clean(t["text"]), t["owner"], day(t["due"]), ST_HUMAN.get(t["st"], ""),
                            pname.get(t["project"], ""), deps]))
        else:
            out.append(tsv([b, t["id"], t["text"], t["owner"], t["due"], t["pri"], t["st"], t["project"],
                            ",".join(t["dep"])]))
    if want and intent != "pending":
        lim = {"today": 0, "week": 7}.get(intent)
        ag = [a for a in c["agenda"] if a["date"] >= today.isoformat()
              and (lim is None or a["date"] <= (today + datetime.timedelta(days=lim)).isoformat())]
        if ag:
            out.append("# agenda")
            out += [tsv([day(a["date"]), clean(a["text"])] if human else [a["date"], a["text"], a["ref"]])
                    for a in sorted(ag, key=lambda a: a["date"])]
    if intent in ("risks", "project"):
        rk = [(p, r) for p in c["projects"] if p["status"] not in P_ARCH and (not focus or p is focus) for r in p["risks"]]
        if rk:
            out.append("# risks")
            for p, r in sorted(rk, key=lambda x: -x[1]["sev"]):
                out.append(tsv([p["name"], clean(r["risk"]), r["sev"], clean(r["mitigation"]), r["owner"]] if human
                               else [p["name"], r["risk"], r["sev"], r["mitigation"], r["owner"], r["id"]]))
    if intent == "project" and focus:
        out.insert(1, tsv(["project", focus["name"], focus["status"], focus["due"]]))
    return "\n".join(out)


def cmd_brief(v, a):
    try:
        print(build_brief(v, a.intent, a.ctx, a.project, a.audience, a.as_of))
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


def set_field(line, key, val):
    pat = re.compile(r" \| %s:[^|]*?(?= \||\s*$)" % re.escape(key))
    if pat.search(line):
        return pat.sub(lambda _: " | %s:%s" % (key, val), line, count=1)
    return line.rstrip() + " | %s:%s" % (key, val)


def atomic_write(path, content):
    """temp+rename so a sync client never sees a partial file"""
    tmp = path.with_name(path.name + ".pa-tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def atomic_edit(path, fn):
    atomic_write(path, fn(path.read_text(encoding="utf-8")))


def report_validate(v):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cmd_validate(Vault(v.root), None)
    if code:
        print("VALIDATE_ERRORS\n" + "\n".join(l for l in buf.getvalue().splitlines() if l.startswith("ERR")))
    return code


def cmd_apply(v, a):
    """dry-run unless --yes. preview text is built from the operation, never by a model."""
    es = a.lang == "es"
    if a.ctx not in v.contexts:
        print("ERR unknown ctx", a.ctx)
        return 1
    if a.due and not ISO.match(a.due):
        print("ERR bad date", a.due)
        return 1
    if a.op == "add":
        if not a.text:
            print("ERR add needs --text")
            return 1
        lines, found = match_report(v, a.ctx, a.text)
        if found and not a.force:
            print("MATCH\n" + "\n".join(lines))
            return 10
        path = v.root / a.ctx / ("tracker.md" if not a.project else "Projects/%s/actions.md" % a.project)
        if (a.project and a.project != slug(a.project)) or not path.exists():
            print("ERR no target for project", a.project)
            return 1
        msg = ('Agregar "%s" (%s)' if es else 'Add "%s" (%s)') % (a.text, nat_date(a.due, a.lang))
        print("PREVIEW" if not a.yes else "APPLIED", msg)
        if a.yes:
            parts = [a.text, "id:" + next_id(v)] + (["@" + a.owner] if a.owner else []) \
                + (["due:" + a.due] if a.due else []) + (["pri:" + a.pri] if a.pri else []) \
                + (["kind:%s" % a.kind, "topic:%s" % a.topic] if not a.project and a.kind and a.topic else []) + ["st:confirmed"]
            atomic_edit(path, lambda s: s.rstrip("\n") + "\n- [ ] " + " | ".join(parts) + "\n")
            return 1 if report_validate(v) else 0
        return 0
    hits = find_tasks(v, a.ctx, a.task, a.match)
    if len(hits) != 1:
        print("AMBIGUOUS" if hits else "NOT_FOUND")
        for x in hits[:5]:
            print(tsv([x["t"].get("id"), x["t"]["text"], x["t"].get("due")]))
        return 3 if hits else 4
    x = hits[0]
    t, n = x["t"], x["line"]

    def change(line):
        if a.op == "done":
            return set_field(line.replace("- [ ]", "- [x]", 1), "st", "done")
        if a.op == "cancel":
            return set_field(line, "st", "cancelled")
        return set_field(line, "due", a.due)
    if a.op == "due" and not a.due:
        print("ERR due needs --due")
        return 1
    msg = {"done": ('Marcar como hecha: "%s"' if es else 'Mark as done: "%s"') % t["text"],
           "cancel": ('Cancelar: "%s"' if es else 'Cancel: "%s"') % t["text"],
           "due": ('Mover "%s" de %s a %s' if es else 'Move "%s" from %s to %s')
           % (t["text"], nat_date(t.get("due"), a.lang), nat_date(a.due, a.lang))}[a.op]
    print("PREVIEW" if not a.yes else "APPLIED", msg)
    if a.yes:
        def edit(s):
            ls = s.split("\n")
            if parse_task(ls[n - 1] if n <= len(ls) else "") is None or parse_task(ls[n - 1]).get("id") != t.get("id"):
                raise RuntimeError("file changed underneath")
            ls[n - 1] = change(ls[n - 1])
            return "\n".join(ls)
        atomic_edit(x["file"], edit)
        if t.get("td"):
            print("TODOIST_SYNC", t["td"])
        return 1 if report_validate(v) else 0
    return 0


PREFS = Path(".pro-assistant/prefs.tsv")
PREF_KEYS = {"length": ("short", "normal"), "format": ("auto", "table", "list"), "diagrams": ("auto", "off"),
             "lang": ("auto", "es", "en"), "tone": ("direct", "formal", "warm")}
PREF_DEFAULT = {"length": "short", "format": "auto", "diagrams": "auto", "lang": "auto", "tone": "direct"}
DIAGRAM_MAX = 12
LEAKS = [("task id", r"\bT-\d+"), ("project id", r"\bPRJ-[A-Z0-9_]+"), ("decision/risk id", r"\b[DR]-\d+"),
         ("raw field", r"\b(?:id|st|td|dep|src|pri|due|ctx|sev|kind|topic):\S"), ("contract", r"\bcontract:\s*v\d"),
         ("file path", r"(?:^|[\s(`])[\w./~-]*\.(?:md|py|tsv|json|html)\b"), ("abs path", r"(?:^|\s)(?:~|/Users|/private)/\S+"),
         ("iso date", r"\b\d{4}-\d{2}-\d{2}\b"), ("tool name", r"\bpa\.py\b|\bvault\b|\bfrontmatter\b")]


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


def build_compose(v, intent, ctx, project=None, as_of=None):
    """single input of the humanizer: rules + prefs + id-free data. holds no id, code or path."""
    prefs = read_prefs(v)
    if prefs["lang"] == "auto" and owner_field(v, "chat_lang") in ("es", "en"):
        prefs["lang"] = owner_field(v, "chat_lang")
    out = ["# template", response_template(intent), "# prefs", " ".join("%s=%s" % kv for kv in prefs.items()),
           "# data", build_brief(v, intent, ctx, project, "human", as_of)]
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
    p = sp.add_parser("apply")
    p.add_argument("op", choices=["done", "cancel", "due", "add"])
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
          "prefs": cmd_prefs, "lint-output": cmd_lint_output}[a.cmd]
    return fn(v, a)


if __name__ == "__main__":
    sys.exit(main())
