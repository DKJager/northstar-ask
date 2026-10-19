# 3Dogs Nexus — authorship fingerprint alexa-plus-v2-eval-runner
"""Blind-pack runner: five business questions, answered before and after a
correction, through the real client.

Default (offline): runs against the hand-written local stub in
tests/fake_service.py. That proves the before / correct / after PATH works
end to end. It says nothing about answer quality, because the stub's text is
canned.

Live (needs a hosted endpoint): set NORTHSTAR_ENDPOINT and NORTHSTAR_TOKEN
and pass --live. The same steps run against the real service and the pairs
are written for blind scoring; nothing is asserted about the wording.

Writes eval/blind_pack/results_<mode>.json. Prints EVAL_OK on success.
"""
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from client.northstar_client import NorthstarClient  # noqa: E402
from northstar import gen_data  # noqa: E402

PACK = os.path.join(ROOT, "eval", "blind_pack")
MARK = "Improved from your feedback"


def ground_truth():
    """Exact answers from the deterministic fictional dataset."""
    products = gen_data.build_products()
    sales = gen_data.build_sales(products)
    cat = {p["product_id"]: p["category"] for p in products}
    name = {p["product_id"]: p["product_name"] for p in products}

    def top(rows, key, value):
        acc = {}
        for r in rows:
            acc[key(r)] = acc.get(key(r), 0.0) + value(r)
        k = max(acc, key=acc.get)
        return k, round(acc[k], 2)

    q2 = [r for r in sales if r["quarter"] == "Q2 2026"]
    q1 = [r for r in sales if r["quarter"] == "Q1 2026"]
    last4 = [r for r in sales if r["quarter"] in ("Q3 2025", "Q4 2025", "Q1 2026", "Q2 2026")]
    y26 = [r for r in sales if r["quarter"] in ("Q1 2026", "Q2 2026")]
    rate = {}
    for r in y26:
        u, ret = rate.get(r["product_id"], (0, 0))
        rate[r["product_id"]] = (u + r["units_sold"], ret + r["units_returned"])
    worst = max(rate, key=lambda p: rate[p][1] / rate[p][0])
    return {
        "q1": {"answer": "Q2 2026 revenue", "value_usd": round(sum(r["revenue_usd"] for r in q2), 2)},
        "q2": dict(zip(("answer", "value_usd"), top(q2, lambda r: r["region"], lambda r: r["revenue_usd"]))),
        "q3": dict(zip(("answer", "value_usd"), top(last4, lambda r: cat[r["product_id"]], lambda r: r["revenue_usd"]))),
        "q4": {"answer": name[worst], "return_rate": round(rate[worst][1] / rate[worst][0], 4)},
        "q5": dict(zip(("answer", "value_usd"), top(q1, lambda r: r["channel"], lambda r: r["revenue_usd"]))),
    }


def run(client, questions, live):
    rows = []
    for q in questions:
        sid = "eval-" + q["id"]
        before = client.ask(sid, q["question"])
        fb = client.feedback(sid, before["answer_id"], q["correction"])
        after = client.ask(sid, q["question"])
        rows.append({"id": q["id"], "question": q["question"], "correction": q["correction"],
                     "before": before, "feedback": fb, "after": after})
        if not live:
            assert MARK not in before["spoken"], q["id"] + ": before-answer already marked"
            assert after["spoken"].startswith(MARK), q["id"] + ": after-answer not marked improved"
            assert after["answer_id"] != before["answer_id"], q["id"] + ": answer id did not change"
    return rows


def main():
    live = "--live" in sys.argv
    with open(os.path.join(PACK, "questions.json"), encoding="utf-8") as fh:
        questions = json.load(fh)["questions"]
    assert len(questions) == 5, "pack must hold exactly 5 questions"
    truth = ground_truth()
    if live:
        client = NorthstarClient(sample_mode=False)
        rows = run(client, questions, True)
        stub = None
    else:
        from tests.fake_service import FakeNorthstarService
        with FakeNorthstarService(mode="ok") as stub:
            client = NorthstarClient(endpoint=stub.url, token="local-eval", sample_mode=False)
            rows = run(client, questions, False)
            seen = [r for r in stub.recorded if r["path"] == "/v1/feedback"]
            assert len(seen) == 5, "five corrections should reach the service"
            for row, rec in zip(rows, seen):
                assert rec["body"]["answer_id"] == row["before"]["answer_id"], "correction must name the before-answer"
                assert rec["body"]["correction"] == row["correction"], "correction text must arrive intact"
    rng = random.Random(20261016)
    blind, key = [], {}
    for row in rows:
        before_is_a = rng.random() < 0.5
        a, b = (row["before"], row["after"]) if before_is_a else (row["after"], row["before"])
        blind.append({"id": row["id"], "question": row["question"],
                      "answer_A": a["spoken"], "answer_B": b["spoken"]})
        key[row["id"]] = {"A": "before" if before_is_a else "after", "B": "after" if before_is_a else "before"}
    mode = "live" if live else "local_fake"
    out = {"mode": mode,
           "note": ("Canned text from a local test double; proves the path only, not answer quality."
                    if not live else "Answers from the hosted service; score blind, then open 'key'."),
           "ground_truth": truth, "blind_pairs": blind, "key": key, "runs": rows}
    path = os.path.join(PACK, "results_%s.json" % mode)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print("wrote", os.path.relpath(path, ROOT), "(%d questions)" % len(rows))
    print("EVAL_OK")


if __name__ == "__main__":
    main()
