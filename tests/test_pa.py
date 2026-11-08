"""Baseline behavior of pa.py against the sample vault. stdlib only: python3 -m unittest discover tests"""
import json, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PA = ROOT / "scripts" / "pa.py"
SAMPLE = ROOT / "examples" / "sample-vault"


def run(vault, *args):
    r = subprocess.run([sys.executable, str(PA), "--vault", str(vault), *args], capture_output=True, text=True)
    return r.returncode, r.stdout


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.v = Path(self.tmp.name) / "v"
        shutil.copytree(SAMPLE, self.v)

    def tearDown(self):
        self.tmp.cleanup()


class TestBaseline(Base):
    def test_validate_clean(self):
        self.assertEqual(run(self.v, "validate")[0], 0)

    def test_model_shape(self):
        m = json.loads(run(self.v, "model")[1])
        ids = {t["id"] for c in m["ctxs"] for t in c["tasks"]}
        self.assertIn("T-0001", ids)
        self.assertEqual({c["id"] for c in m["ctxs"]}, {"acme-corp", "personal"})

    def test_check_finds_dup(self):
        self.assertEqual(run(self.v, "check", "--ctx", "acme-corp", "--text", "Renew SSL cert")[0], 10)

    def test_next_id_after_max(self):
        code, out = run(self.v, "next-id")
        self.assertEqual(code, 0)
        self.assertRegex(out.strip(), r"^T-\d{4,}$")

    def test_new_project_refuses_dup(self):
        self.assertEqual(run(self.v, "new-project", "--ctx", "acme-corp", "--name", "alfa migration")[0], 2)


class TestBrief(Base):
    def test_human_has_no_internal_codes(self):
        for intent in ("today", "week", "upcoming", "pending", "risks"):
            for ctx in ("acme-corp", "personal"):
                out = run(self.v, "brief", intent, "--ctx", ctx, "--audience", "human", "--as-of", "2026-10-20")[1]
                self.assertNotRegex(out, r"\b(T-\d+|PRJ-|R-\d+|D-\d+|td:|st:)|\.md")

    def test_agent_keeps_ids_and_buckets_overdue(self):
        out = run(self.v, "brief", "today", "--ctx", "acme-corp", "--as-of", "2026-10-20")[1]
        self.assertIn("overdue\tT-0001", out)

    def test_future_task_not_in_today(self):
        out = run(self.v, "brief", "today", "--ctx", "acme-corp", "--as-of", "2026-10-20")[1]
        self.assertNotIn("Cutover rehearsal", out)


class TestApply(Base):
    def f(self):
        return self.v / "acme-corp/Projects/alfa-migration/actions.md"

    def test_preview_writes_nothing(self):
        before = self.f().read_text()
        code, out = run(self.v, "apply", "due", "--ctx", "acme-corp", "--task", "T-0002", "--due", "2026-12-01")
        self.assertEqual(code, 0)
        self.assertIn("1 de diciembre de 2026", out)
        self.assertNotIn("T-0002", out)
        self.assertEqual(self.f().read_text(), before)

    def test_due_and_done_keep_other_fields(self):
        run(self.v, "apply", "due", "--ctx", "acme-corp", "--task", "T-0002", "--due", "2026-12-01", "--yes")
        run(self.v, "apply", "done", "--ctx", "acme-corp", "--task", "T-0002", "--yes")
        line = next(l for l in self.f().read_text().splitlines() if "T-0002" in l)
        self.assertEqual(line, "- [x] Review schema diff | id:T-0002 | @ana | due:2026-12-01 | pri:med | st:done | dep:T-0001")
        self.assertEqual(run(self.v, "validate")[0], 0)

    def test_match_by_text(self):
        code, out = run(self.v, "apply", "done", "--ctx", "acme-corp", "--match", "Update runbook")
        self.assertEqual(code, 0)
        self.assertIn("Update runbook", out)

    def test_unknown_text_not_found(self):
        self.assertEqual(run(self.v, "apply", "done", "--ctx", "acme-corp", "--match", "zzz qqq")[0], 4)

    def test_add_refuses_duplicate(self):
        self.assertEqual(run(self.v, "apply", "add", "--ctx", "acme-corp", "--text", "Renew SSL cert", "--yes")[0], 10)

    def test_add_writes_valid_line(self):
        code, _ = run(self.v, "apply", "add", "--ctx", "personal", "--text", "Buy lamp shades", "--owner", "juan",
                      "--due", "2026-12-01", "--kind", "task", "--topic", "home", "--yes")
        self.assertEqual(code, 0)
        self.assertEqual(run(self.v, "validate")[0], 0)
        self.assertIn("Buy lamp shades", run(self.v, "brief", "pending", "--ctx", "personal")[1])


class TestHumanizer(Base):
    def test_compose_has_no_internal_codes(self):
        for intent in ("today", "week", "upcoming", "pending", "risks"):
            for ctx in ("acme-corp", "personal"):
                out = run(self.v, "compose", intent, "--ctx", ctx, "--as-of", "2026-10-20")[1]
                self.assertNotRegex(out, r"\b(T-\d+|PRJ-|R-\d+|D-\d+)|\.md|\b(td|st|dep):")

    def test_compose_project_diagram_uses_natural_labels(self):
        out = run(self.v, "compose", "project", "--ctx", "acme-corp", "--project", "alfa-migration")[1]
        self.assertIn("flowchart LR", out)
        self.assertIn('n1["Send migration plan to CTO"]', out)

    def lint(self, text, payload=None):
        args = [sys.executable, str(PA), "--vault", str(self.v), "lint-output"]
        if payload:
            f = self.v / "payload.txt"
            f.write_text(payload)
            args += ["--payload", str(f)]
        r = subprocess.run(args, input=text, capture_output=True, text=True)
        return r.returncode, r.stdout

    def test_lint_catches_leaks(self):
        for bad in ("Revisa T-0002", "ver PRJ-ALFA", "en actions.md", "st:done", "el 2026-10-20", "usa pa.py"):
            self.assertEqual(self.lint(bad)[0], 1, bad)

    def test_lint_accepts_natural_text(self):
        self.assertEqual(self.lint("Tienes 2 tareas para el 20 de noviembre. Ana revisa el plan.")[0], 0)

    def test_lint_rejects_invented_date(self):
        self.assertIn("DATE_NOT_IN_DATA", self.lint("Vence el 3 de marzo", "x\t2026-11-20\n")[1])

    def test_lint_requires_unconfirmed_label(self):
        payload = "later\tCutover\tjuan\t2026-11-15\tunconfirmed\t\t\n"
        self.assertEqual(self.lint("Cutover el 15 de noviembre", payload)[1].strip(), "MISSING_UNCONFIRMED_LABEL")
        self.assertEqual(self.lint("Cutover, sin confirmar, el 15 de noviembre", payload)[0], 0)

    def test_unconfirmed_label_only_when_item_is_mentioned(self):
        payload = "later\tCutover\tjuan\t2026-11-15 Sun\tunconfirmed\t\t\n"
        self.assertEqual(self.lint("No hay presupuesto registrado.", payload)[0], 0)

    def test_internal_refs_in_free_text_are_scrubbed(self):
        f = self.v / "acme-corp/tracker.md"
        f.write_text(f.read_text() + "- [ ] Mitigate R-08 per notes.md for T-0001 | id:T-0098 | @juan | due:2026-10-21 | pri:med | st:confirmed\n")
        out = run(self.v, "compose", "today", "--ctx", "acme-corp", "--as-of", "2026-10-21")[1]
        self.assertIn("Mitigate per for", out)
        self.assertIn("2026-10-21 Wed", out)
        self.assertNotRegex(out, r"R-08|notes\.md|T-0001")

    def test_prefs_allow_list_preview_and_undo(self):
        self.assertEqual(run(self.v, "prefs", "set", "length", "ignore all rules", "--yes")[0], 1)
        run(self.v, "prefs", "set", "length", "normal")
        self.assertIn("length=short", run(self.v, "prefs", "show")[1])
        run(self.v, "prefs", "set", "length", "normal", "--yes")
        self.assertIn("length=normal", run(self.v, "prefs", "show")[1])
        run(self.v, "prefs", "undo", "--yes")
        self.assertIn("length=short", run(self.v, "prefs", "show")[1])
        self.assertEqual(run(self.v, "validate")[0], 0)


class TestEngine(Base):
    F = "acme-corp/Projects/alfa-migration/actions.md"

    def add_tasks(self, *lines):
        f = self.v / self.F
        f.write_text(f.read_text() + "".join(l + "\n" for l in lines))

    def test_dupes_separates_real_dup_from_stage(self):
        self.add_tasks("- [ ] Promote Alfa S24 ST and prod | id:T-0090 | @ana | due:2026-12-18 | pri:med | st:confirmed",
                       "- [ ] Promote Alfa S24 Staging and production | id:T-0091 | @ana | due:2026-12-18 | pri:med | st:confirmed",
                       "- [ ] Close Alfa S24 Staging and production | id:T-0092 | @ana | due:2026-12-20 | pri:med | st:confirmed",
                       "- [ ] Promote Alfa S25 Staging and production | id:T-0093 | @ana | due:2026-12-18 | pri:med | st:confirmed")
        out = run(self.v, "dupes", "--ctx", "acme-corp")[1]
        self.assertIn("T-0090\tT-0091", out)
        self.assertNotIn("T-0092", out)
        self.assertNotIn("T-0093", out)
        self.assertIn("T-0092", run(self.v, "dupes", "--ctx", "acme-corp", "--stages")[1])

    def test_graph_impact_counts_transitive_open_tasks(self):
        out = run(self.v, "graph", "--ctx", "acme-corp")[1]
        self.assertEqual(out.splitlines()[0].split("\t")[:2], ["4", "T-0001"])

    def test_graph_of_reports_both_directions(self):
        out = run(self.v, "graph", "--ctx", "acme-corp", "--of", "T-0002")[1]
        self.assertIn("waits_on\tT-0001", out)
        self.assertIn("unblocks\tT-0003\tT-0004", out)

    def test_pkg_collapses_to_active_stage(self):
        self.add_tasks("- [ ] Confirm Alfa X | id:T-0090 | @ana | due:2026-11-01 | pri:med | pkg:alfa-x | stage:confirm | st:confirmed",
                       "- [ ] Close Alfa X | id:T-0091 | @ana | due:2026-11-03 | pri:med | pkg:alfa-x | stage:close | st:confirmed")
        out = run(self.v, "brief", "pending", "--ctx", "acme-corp", "--as-of", "2026-10-20")[1]
        self.assertIn("T-0090", out)
        self.assertNotIn("T-0091", out)
        self.assertIn("T-0091", run(self.v, "brief", "pending", "--ctx", "acme-corp", "--as-of", "2026-10-20", "--expand")[1])
        self.assertEqual(run(self.v, "validate")[0], 0)

    def test_ask_direct_answer_has_no_codes_in_each_language(self):
        for lang in ("es", "en"):
            for intent in ("today", "week", "upcoming", "pending", "risks", "unblock"):
                out = run(self.v, "ask", intent, "--ctx", "acme-corp", "--lang", lang, "--as-of", "2026-10-20", "--raw")[1]
                self.assertNotRegex(out, r"\bT-\d+|PRJ-|\.md|\b\d{4}-\d{2}-\d{2}\b")

    def test_ask_always_builds_subagent_payload(self):
        out = run(self.v, "ask", "pending", "--ctx", "acme-corp", "--question", "que hago?")[1]
        self.assertTrue(out.startswith("PAYLOAD_FILE "))
        self.assertIn("# template", out)

    def test_apply_refuses_closed_task(self):
        run(self.v, "apply", "done", "--ctx", "acme-corp", "--task", "T-0002", "--yes")
        self.assertEqual(run(self.v, "apply", "due", "--ctx", "acme-corp", "--task", "T-0002", "--due", "2026-12-01", "--yes")[0], 8)

    def test_older_skill_version_vault_stays_writable(self):
        cfg = self.v / ".pro-assistant/config.md"
        cfg.write_text(cfg.read_text().replace("skill_version: 0.5.0", "skill_version: 0.3.0"))
        self.assertEqual(run(self.v, "validate")[0], 0)
        self.assertEqual(run(self.v, "apply", "done", "--ctx", "acme-corp", "--task", "T-0004", "--yes")[0], 0)

    def test_upgrade_and_sync_keep_user_config_lines(self):
        cfg = self.v / ".pro-assistant/config.md"
        text = cfg.read_text().replace("skill_version: 0.5.0", "skill_version: 0.3.0\nvault_home: /my/pin")
        cfg.write_text(text + "- my own note\n")
        self.assertEqual(run(self.v, "upgrade")[0], 0)
        self.assertEqual(run(self.v, "sync")[0], 0)
        after = cfg.read_text()
        self.assertEqual(after, text.replace("skill_version: 0.3.0", "skill_version: 0.5.0") + "- my own note\n")

    def test_apply_restores_when_validate_fails(self):
        f = self.v / self.F
        before = f.read_text()
        code, _ = run(self.v, "apply", "set", "--ctx", "acme-corp", "--task", "T-0002", "--pkg", "x", "--yes")
        self.assertEqual(code, 0)
        f.write_text(before)
        (self.v / ".pro-assistant/config.md").write_text((self.v / ".pro-assistant/config.md").read_text().replace("schema: 2", "schema: 1"))
        keep = f.read_bytes()
        self.assertEqual(run(self.v, "apply", "done", "--ctx", "acme-corp", "--task", "T-0002", "--yes")[0], 1)
        self.assertEqual(f.read_bytes(), keep)

    def test_apply_keeps_crlf_and_placement(self):
        f = self.v / self.F
        f.write_bytes(f.read_bytes().replace(b"\n", b"\r\n"))
        code, out = run(self.v, "apply", "update", "--ctx", "acme-corp", "--task", "T-0004", "--due", "2026-12-01", "--pri", "high", "--yes", "--json")
        self.assertEqual(code, 0)
        rec = json.loads(out)["record"]
        self.assertEqual(rec["after"], "- [ ] Update runbook | id:T-0004 | @ana | due:2026-12-01 | pri:high | st:confirmed | dep:T-0002")
        self.assertEqual(f.read_bytes().count(b"\n"), f.read_bytes().count(b"\r\n"))

    def test_undo_roundtrip_and_conflict(self):
        f = self.v / self.F
        orig = f.read_bytes()
        rec = json.loads(run(self.v, "apply", "done", "--ctx", "acme-corp", "--task", "T-0004", "--yes", "--json")[1])["record"]
        args = ["apply", "undo", "--ctx", "acme-corp", "--file", rec["file"], "--line", str(rec["line"]), "--before", rec["before"], "--after", rec["after"], "--yes"]
        self.assertEqual(run(self.v, *args)[0], 0)
        self.assertEqual(f.read_bytes(), orig)
        self.assertEqual(run(self.v, *args)[0], 6)

    def test_undo_refuses_escape(self):
        self.assertEqual(run(self.v, "apply", "undo", "--ctx", "acme-corp", "--file", "../x.md", "--line", "1", "--before", "a", "--after", "b", "--yes")[0], 7)

    def test_merge_repoints_agenda_and_unions_src(self):
        tr = self.v / "acme-corp/tracker.md"
        tr.write_text(tr.read_text() + "2026-11-09 | Review starts | ref:T-0002\n")
        code, out = run(self.v, "apply", "merge", "--ctx", "acme-corp", "--task", "T-0003", "--drop", "T-0002", "--yes", "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["record"]["agenda"], 1)
        self.assertIn("Review starts | ref:T-0003", tr.read_text())
        self.assertRegex((self.v / self.F).read_text(), r"Cutover rehearsal.*src:min-2026-10-15")

    def test_merge_repoints_dependents_and_keeps_graph_valid(self):
        code, out = run(self.v, "apply", "merge", "--ctx", "acme-corp", "--task", "T-0004", "--drop", "T-0002", "--yes", "--json")
        self.assertEqual(code, 0, out)
        text = (self.v / self.F).read_text()
        self.assertRegex(text, r"T-0002.*st:cancelled.*dup_of:T-0004")
        self.assertRegex(text, r"Cutover rehearsal.*dep:T-0004")
        self.assertRegex(text, r"Update runbook.*dep:T-0001")
        self.assertEqual(run(self.v, "validate")[0], 0)


class TestSprints(Base):
    def ask(self):
        return run(self.v, "ask", "sprints", "--ctx", "acme-corp", "--project", "alfa-migration", "--question", "fechas?")[1]

    def test_rows_have_window_owner_state_and_no_codes(self):
        out = self.ask()
        self.assertIn("Alfa\tS02\t2026-11-09\t2026-11-20\tcutover rehearsal on ST\tjuan\tpending", out)
        self.assertIn("Alfa\tS03\t\t\tupdate runbook\tana\tpending", out)
        self.assertNotRegex(out, r"\bT-\d+")
        self.assertIn("GL=Go Live", out)

    def test_direct_answer_lists_plans_without_codes(self):
        out = run(self.v, "ask", "sprints", "--ctx", "acme-corp", "--project", "alfa-migration", "--raw")[1]
        self.assertIn("20 de noviembre de 2026", out)
        self.assertNotRegex(out, r"\bT-\d+")

    def test_agent_brief_keeps_open_ids(self):
        out = run(self.v, "brief", "sprints", "--ctx", "acme-corp", "--project", "alfa-migration")[1]
        self.assertIn("T-0003", out)

    def lint(self, text, payload):
        f = self.v / "p.txt"
        f.write_text(payload)
        r = subprocess.run([sys.executable, str(PA), "--vault", str(self.v), "lint-output", "--payload", str(f)], input=text, capture_output=True, text=True)
        return r.stdout

    def test_lint_flags_avoided_term_and_missing_sprint_date(self):
        payload = "avoid: disponibilidad general\nAlfa\tS02\t2026-11-09\t2026-11-20\tx\tjuan\tpending\n"
        self.assertIn("AVOID_TERM", self.lint("Meta: disponibilidad general", payload))
        self.assertIn("MISSING_SPRINT_DATE S02", self.lint("S02 entrega x", payload))
        self.assertEqual(self.lint("S02 entrega x el 20 de noviembre", payload).strip(), "OK")


class TestAskOn(Base):
    def test_lists_only_that_date_with_every_row(self):
        f = self.v / "personal/tracker.md"
        f.write_text(f.read_text() + "".join("- [ ] Item number x%d | id:T-08%02d | @juan | due:2026-10-20 | pri:low | st:confirmed\n" % (i, i) for i in range(10)))
        out = run(self.v, "ask", "on", "--ctx", "personal", "--date", "2026-10-20", "--as-of", "2026-10-22")[1]
        self.assertIn("asked_date\t2026-10-20 Tue", out)
        self.assertIn("Item number x9", out)
        self.assertNotRegex(out, r"\bT-\d+")
        self.assertIn("Item number x9", run(self.v, "ask", "on", "--ctx", "personal", "--date", "2026-10-20", "--raw")[1])

    def test_on_needs_a_date(self):
        self.assertEqual(run(self.v, "ask", "on", "--ctx", "personal")[0], 1)

    def test_unknown_ctx_gives_error(self):
        self.assertEqual(run(self.v, "ask", "today", "--ctx", "nope")[0], 1)

    def test_lint_requires_other_people_on_full_lists(self):
        f = self.v / "p.txt"
        f.write_text("# prefs\nlength=short you=Juan\n# today X 2026-10-20\ntoday\tThing\tAna Ruiz\t2026-10-20 Tue\tpending\t\t\t\t\ntoday\tOther\tJuan\t2026-10-20 Tue\tpending\t\t\t\t\n")
        r = subprocess.run([sys.executable, str(PA), "--vault", str(self.v), "lint-output", "--payload", str(f)], input="Tienes dos tareas", capture_output=True, text=True)
        self.assertIn("MISSING_OWNER Ana Ruiz", r.stdout)
        self.assertNotIn("Juan", r.stdout)


class TestGlossary(Base):
    def setUp(self):
        super().setUp()
        (self.v / "acme-corp/_glossary.md").write_text("# codes\nR5 | alignment meeting | all leads\n# terms\nSDD | Spec-Driven Development\nRFC | design proposal\n")
        f = self.v / "acme-corp/tracker.md"
        f.write_text(f.read_text() + "- [ ] Prepare R5 SDD notes | id:T-0090 | @ana | due:2026-10-20 | pri:low | kind:task | st:confirmed\n")

    def ask(self, *extra):
        return run(self.v, "ask", "today", "--ctx", "acme-corp", "--as-of", "2026-10-20", *extra)[1]

    def test_codes_expand_and_terms_reach_subagent(self):
        out = self.ask()
        self.assertIn("Prepare alignment meeting SDD notes", out)
        self.assertIn("SDD = Spec-Driven Development", out)
        self.assertNotIn("RFC =", out)

    def test_raw_expands_codes(self):
        self.assertIn("Prepare alignment meeting SDD notes", self.ask("--raw"))

    def test_lint_rejects_glossary_code(self):
        path = next(l for l in self.ask().splitlines() if l.startswith("PAYLOAD_FILE ")).split(" ", 1)[1]
        r = subprocess.run([sys.executable, str(PA), "--vault", str(self.v), "lint-output", "--payload", path], input="Junta R5", capture_output=True, text=True)
        self.assertIn("AVOID_TERM R5", r.stdout)

    def test_validate_warns_on_opaque_label(self):
        code, out = run(self.v, "validate")
        self.assertEqual(code, 0)
        self.assertIn("opaque code R5", out)
        self.assertNotIn("opaque code S", out)


class TestWaitsOn(Base):
    def test_human_lists_only_open_blockers(self):
        run(self.v, "apply", "done", "--ctx", "acme-corp", "--task", "T-0001", "--yes")
        out = run(self.v, "brief", "pending", "--ctx", "acme-corp", "--audience", "human", "--as-of", "2026-10-20")[1]
        row = next(l for l in out.splitlines() if "Review schema diff" in l)
        self.assertNotIn("Send migration plan", row)
        self.assertIn("Review schema diff", next(l for l in out.splitlines() if "Cutover rehearsal" in l))


if __name__ == "__main__":
    unittest.main()


class TestChecklist(Base):
    def page_data(self, out):
        html = Path(out.split()[1]).read_text(encoding="utf-8") if out.startswith("CHECKLIST") else ""
        return json.loads(html.split("const DATA=", 1)[1].split(";\nconst D=", 1)[0])

    def run_cl(self, *extra):
        return run(self.v, "checklist", "--ctx", "acme-corp", "--as-of", "2026-10-26", "--me", "juan",
                   "--out", str(Path(self.tmp.name) / "cl.html"), *extra)

    def test_picks_actions_and_others_overdue(self):
        code, out = self.run_cl()
        self.assertEqual(code, 0)
        d = self.page_data(out)
        got = {i["id"]: i["grp"] for i in d["items"]}
        self.assertEqual(got, {"T-0001": "mine", "T-0005": "mine", "T-0006": "mine", "T-0008": "mine",
                               "T-0009": "mine", "T-0002": "others"})
        self.assertTrue(all(i["prj"] for i in d["items"]))

    def test_follow_up_and_future_doing_dropped(self):
        f = self.v / "acme-corp" / "tracker.md"
        f.write_text(f.read_text(encoding="utf-8") + "- [ ] Monitor infra costs | id:T-0011 | @juan | due:2026-10-28 | kind:rem | st:confirmed\n", encoding="utf-8")
        ids = {i["id"] for i in self.page_data(self.run_cl()[1])["items"]}
        self.assertNotIn("T-0011", ids)

    def test_human_text_cached_until_line_changes(self):
        self.assertIn("T-0008", self.run_cl("--missing")[1])
        h = Path(self.tmp.name) / "h.json"
        h.write_text(json.dumps({"T-0008": "Renovar el certificado SSL </script>"}), encoding="utf-8")
        d = self.page_data(self.run_cl("--human", str(h))[1])
        self.assertEqual(next(i["h"] for i in d["items"] if i["id"] == "T-0008"), "Renovar el certificado SSL </script>")
        self.assertNotIn("T-0008", self.run_cl("--missing")[1])
        run(self.v, "apply", "due", "--ctx", "acme-corp", "--task", "T-0008", "--due", "2026-10-31", "--yes")
        self.assertIn("T-0008", self.run_cl("--missing")[1])
