# CookMemory (comparison build)

A persistent procedural-memory harness evaluated on CaptainCook4D egocentric
recordings. The goal is to remember unresolved mistakes through a long task
and improve which evidence an agent checks before advancing.

This repo is a **comparison build**: it starts from the
[shravanthi-m/MongoHack](https://github.com/shravanthi-m/MongoHack) starter
(public, built during the MongoDB Harness Engineering & Model Wrangling
Hackathon on 2026-09-26) and applies an improvement patch on top, so the two
can be compared side by side. Original starter code is credited to its author;
the additions below were built for this comparison.

## What the patch adds

- `cookmemory/evaluate.py` + `cookmemory compare`: evaluator-only scoring
  (caught/missed/false alarms/issue survival) and a memory-vs-stateless table.
- `cookmemory/policy.py` + `propose-policy` / `validate-policy`: a bounded
  recursive-harnessing loop. One rule template (`strict_order`) is proposed
  from measured dev errors, validated against held-out recordings, and
  promoted versioned. The harness only changes its own verification rule when
  the numbers justify it.
- `cookmemory/render.py` + `render-ui`: a self-contained replay page
  (`demo.html`) with a memory/stateless toggle. No external assets.
- `cookmemory/verify_atlas.py`: guided Atlas Sandbox restart-recovery demo
  with a PASS/FAIL verdict.
- `replay` gains `--decisions-out` and `--policy`.

## Quick start

Python 3.10+. Local mode needs no dependencies or API keys.

```bash
# Memory vs stateless comparison table
python3 -m cookmemory.cli compare \
  --events examples/observations.jsonl \
  --labels examples/synthetic-labels.jsonl \
  --decisions-out work/decisions

# Replay UI
python3 -m cookmemory.cli render-ui \
  --events examples/observations.jsonl \
  --memory work/decisions/memory.jsonl \
  --stateless work/decisions/stateless.jsonl \
  --out demo.html
# open demo.html in a browser

# Tests
python3 -m unittest discover -s tests -v
```

## Recursive-harnessing loop

```bash
python3 -m cookmemory.cli compare --events examples/observations-order.jsonl \
  --labels examples/order-labels.jsonl --tag dev-base --json-out work/metrics
python3 -m cookmemory.cli propose-policy --order-missed 2 \
  --requires '{"step-b": ["step-a"]}' --out work/policy-proposed.json
python3 -m cookmemory.cli compare --events examples/observations-order.jsonl \
  --labels examples/order-labels.jsonl --policy work/policy-proposed.json \
  --tag dev-cand --json-out work/metrics
python3 -m cookmemory.cli compare --events examples/observations.jsonl \
  --labels examples/synthetic-labels.jsonl --tag ho-base --json-out work/metrics
python3 -m cookmemory.cli compare --events examples/observations.jsonl \
  --labels examples/synthetic-labels.jsonl --policy work/policy-proposed.json \
  --tag ho-cand --json-out work/metrics
python3 -m cookmemory.cli validate-policy --policy work/policy-proposed.json \
  --dev-baseline work/metrics/dev-base-memory.json \
  --dev-candidate work/metrics/dev-cand-memory.json \
  --heldout-baseline work/metrics/ho-base-memory.json \
  --heldout-candidate work/metrics/ho-cand-memory.json
```

## Atlas Sandbox

```bash
python -m pip install -e '.[atlas]'
export MONGODB_URI='...'          # hackathon Sandbox URI
export MONGODB_DATABASE=cookmemory
python -m cookmemory.verify_atlas examples/observations.jsonl
```

Never commit credentials. `.env.example` documents the variables.

## Honest claims

The bundled fixtures are synthetic and hand-authored for demo purposes; the
replay UI says so on the page. There is no video model, trained error
detector, or real-data benchmark result here. What is real: the memory
plumbing, the evaluator, the policy loop mechanics, and the Atlas checkpoint
code. CaptainCook4D recordings/annotations are external research inputs; cite
Peddi et al., *CaptainCook4D: A Dataset for Understanding Errors in Procedural
Activities*, NeurIPS 2024.
