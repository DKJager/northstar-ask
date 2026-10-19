# 3Dogs Nexus — authorship fingerprint alexa-plus-v2-tests-eval
"""Blind-pack runner test. Prints EVAL_TEST_OK.

(i)  the runner completes against the local stub and writes blind pairs whose
     key is consistent with the stored runs;
(ii) negative control: against a stub that discards corrections, the runner
     must fail its own 'improved' check.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def check(condition, label):
    if not condition:
        raise AssertionError("FAILED: " + label)
    print("  ok - " + label)


class _DeafSet(set):
    """A corrections store that forgets everything it is given."""
    def add(self, item):
        pass


def main():
    proc = subprocess.run([sys.executable, os.path.join(ROOT, "eval", "run_eval.py")],
                          capture_output=True, text=True, timeout=120)
    check(proc.returncode == 0 and "EVAL_OK" in proc.stdout, "run_eval completes against the local stub")
    path = os.path.join(ROOT, "eval", "blind_pack", "results_local_fake.json")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    check(len(data["blind_pairs"]) == 5 and len(data["ground_truth"]) == 5, "five blind pairs and five ground truths")
    for pair in data["blind_pairs"]:
        k = data["key"][pair["id"]]
        run = next(r for r in data["runs"] if r["id"] == pair["id"])
        label_after = "A" if k["A"] == "after" else "B"
        check(pair["answer_" + label_after] == run["after"]["spoken"], pair["id"] + ": key points at the after answer")
    check("canned" in data["note"].lower(), "the results file says the text is canned")

    from client.northstar_client import NorthstarClient
    from tests.fake_service import FakeNorthstarService
    sys.path.insert(0, os.path.join(ROOT, "eval"))
    import run_eval
    with open(os.path.join(ROOT, "eval", "blind_pack", "questions.json"), encoding="utf-8") as fh:
        questions = json.load(fh)["questions"]
    with FakeNorthstarService(mode="ok") as stub:
        stub._server._corrected = _DeafSet()
        client = NorthstarClient(endpoint=stub.url, token="x", sample_mode=False)
        try:
            run_eval.run(client, questions, False)
        except AssertionError:
            check(True, "a stub that ignores corrections makes the runner fail")
        else:
            raise AssertionError("FAILED: runner passed against a stub that ignores corrections")
    print("EVAL_TEST_OK")


if __name__ == "__main__":
    main()
