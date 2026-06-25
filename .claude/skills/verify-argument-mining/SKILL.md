---
name: verify-argument-mining
description: Smoke-test the ClaimDetector and StanceClassifier inference wrappers across all six Noesis content types (news, blog, paper, transcript, book, note). Prints per-sentence claim and stance predictions in a readable table. Works in heuristic mode (no trained model required) and switches to the fine-tuned model automatically when weights are present in models/. Use when iterating on the heuristic rules, after training a new checkpoint, or to confirm inference works end-to-end on all content types.
---

# verify-argument-mining skill

Runs the `ClaimDetector` and `StanceClassifier` inference wrappers against six
sample documents (one per Noesis source type) and prints a per-sentence
prediction table.  No API server, no trained model, and no network needed —
works immediately with the heuristic fallback.

**All paths are relative to the repo root** (`/home/Ikey/NeuroNews`).

## Usage

```bash
python3 .claude/skills/verify-argument-mining/verify.py [--topic TOPIC]
```

`--topic` overrides the per-sample stance topic for all six documents (useful
when checking a specific domain, e.g. `--topic "climate policy"`).

## Example output

```
────────────────────────────────────────────────────────────────────────
  Argument Mining — inference smoke-test
────────────────────────────────────────────────────────────────────────
  ClaimDetector:    heuristic fallback
  StanceClassifier: heuristic fallback

  [news]  topic='economic policy'  (3 sentences)
  Sentence                                                 Claim    Conf  Stance      Conf
  ──────────────────────────────────────────────────────── ──────── ─────  ──────────  ─────
  The unemployment rate fell to 3.8% in March, the low…   CLAIM    0.85  neutral     0.65
  The central bank raised interest rates by 25 basis p…   CLAIM    0.80  neutral     0.65
  Critics argue the government has not done enough to …   —        0.55  critical    0.65

  [blog]  topic='platform changes'  (3 sentences)
  ...

────────────────────────────────────────────────────────────────────────
  RESULT: PASS — all 6 source types produced predictions
  NOTE: heuristic mode — run training scripts once #109 data lands ...
────────────────────────────────────────────────────────────────────────
```

Exit code `0` = PASS (all source types returned predictions without error),
`1` = FAIL (at least one source type raised an exception).

## When to use

| Scenario | Action |
|---|---|
| Iterating on heuristic rules in `models.py` | Run after each edit to see how predictions change |
| After training a new checkpoint | Run to confirm the model loads and produces valid labels |
| Debugging a wrong prediction | Copy the offending sentence into `predict_text()` and add a test |
| Cross-type spot-check | Run with `--topic "your topic"` to see stance consistency |

## Reading the output

- **Claim / —**: `CLAIM` = `is_claim=True`; `—` = not a factual claim.
- **Conf**: probability assigned to the predicted class (0–1).  Heuristic
  scores cluster around 0.5–0.9; trained model scores are sharper.
- **Stance**: `supportive | critical | neutral | ambiguous` relative to the topic.

## Requirements

- No extra packages beyond the standard project dependencies.
- `transformers` is only imported if a trained model checkpoint is present
  (`models/claim_detector/config.json` or `models/stance_classifier/config.json`).

## Training the models

Once the #109 dataset is available under `data/argument_mining/`:

```bash
python -m src.argument_mining.train_claim --data data/argument_mining
python -m src.argument_mining.train_stance --data data/argument_mining
```

Both scripts save the model to `models/{claim_detector,stance_classifier}/` and
write `eval_metrics.json` with overall + per-source-type F1 scores.  Re-run
this skill afterward to confirm the trained model is picked up.
