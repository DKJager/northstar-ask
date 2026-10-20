# Blind pack: before / after a correction

Five realistic business questions over the fictional Northstar Outdoor Co.
dataset (`questions.json`). For each one the runner:

1. asks the question,
2. sends a correction through the same feedback call the "correct me" tool uses,
3. asks the same question again in the same session.

Run it with `python eval/run_eval.py` (needs the packages in
`requirements.txt`). It writes `blind_pack/results_local_fake.json`.

## What the local run proves

The default run points the real client at the hand-written stub in
`tests/fake_service.py`. It proves that the plumbing works from one end to
the other: the correction reaches the service naming the earlier answer, and
the second answer comes back marked "Improved from your feedback" with a new
answer id. `tests/test_eval.py` runs it and also checks that a stub which
ignores corrections makes the runner fail.

## What it does not prove

The stub returns canned text, and the "improved" marker is something the stub
adds itself. Nothing here measures whether an answer got better, or whether
answers are right. Those numbers need the hosted answering service. Until it
is reachable there are no live-engine results, and none are claimed.

## Scoring a live run

Set `NORTHSTAR_ENDPOINT` and `NORTHSTAR_TOKEN`, then run
`python eval/run_eval.py --live`. The output holds:

- `blind_pairs`: each question with two answers labelled A and B in random
  order (seeded), for a scorer who does not know which is which;
- `ground_truth`: exact figures computed from the deterministic dataset, for
  checking the numbers;
- `key`: which label was the before answer. Open it only after scoring.

The responses in `samples/responses.json` are illustrative precomputed
samples for the offline demo. Their figures are not reconciled with the
generated dataset, so do not score them against `ground_truth`.
