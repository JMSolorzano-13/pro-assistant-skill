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
        for bad in ("Revisa T-0002", "ver PRJ-ALFA", "en actions.md", "st:done", "contract: v1", "el 2026-10-20", "usa pa.py"):
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


if __name__ == "__main__":
    unittest.main()
