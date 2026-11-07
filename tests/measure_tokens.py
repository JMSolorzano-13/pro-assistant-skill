"""Estimate tokens the agent loads per query: files per references/intents.md vs `pa.py brief`.
chars/4 estimate (no tokenizer dependency): valid for ratios, not absolute cost.
usage: measure_tokens.py <vault> [as-of]"""
import datetime, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import pa


def est(s):
    return len(s) // 4


def rd(*paths):
    return "".join(p.read_text(encoding="utf-8") for p in paths if p.exists())


def main():
    v = pa.Vault(sys.argv[1])
    asof = sys.argv[2] if len(sys.argv) > 2 else datetime.date.today().isoformat()
    tot = [0, 0, 0]
    print("query\tfiles\tagent\thuman")
    for n, ctx in enumerate(v.contexts):
        prj = [d for d, f in v.projects(ctx) if f and f.get("status") in pa.P_OPEN]
        tr = v.root / ctx / "tracker.md"
        act = [d / "actions.md" for d in prj]
        idx = [d / "index.md" for d in prj]
        risk = [d / f for d in prj for f in ("index.md", "actions.md", "risks.md", "decisions.md")]
        for intent, files in (("today", [tr] + act), ("week", [tr] + act), ("upcoming", [tr] + act + idx),
                              ("pending", act), ("risks", risk)):
            row = [est(rd(*files))] + [est(pa.build_brief(v, intent, ctx, None, a, asof)) for a in ("agent", "human")]
            print("c%d-%s\t%d\t%d\t%d" % (n, intent, *row))
            tot = [x + y for x, y in zip(tot, row)]
    print("TOTAL\t%d\t%d\t%d" % tuple(tot))
    print("saving agent %.0f%% human %.0f%%" % (100 * (1 - tot[1] / tot[0]), 100 * (1 - tot[2] / tot[0])))


main()
