# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A **universal metrics-analyst agent**. It ingests a fixed-shape JSON document of
hierarchical metrics, loads it into in-memory SQLite, enriches it with derived
analytics, and answers questions through an interactive CLI chat. Call-center
metrics (`test_metrics.json`) are just one example — the same code handles metrics
for developers, managers, executives, etc. Nothing hardcodes specific metric names.

## Commands

```bash
# One-time setup (Python 3.12 — langchain 1.x needs 3.10+)
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/pip install -e .

# Start PostgreSQL with pgvector
docker compose up -d

# Configure: copy and fill in credentials
cp .env.example .env

# Run the analyst (MUST run from the project root — top-level `config.py` is imported by name)
.venv/bin/python -m analyzer.cli [path-to-json]   # defaults to test_metrics.json

# Regenerate sample data (standalone, stdlib only)
python3 gen_metrics.py    # NOTE: writes to a hardcoded /mnt/user-data/outputs/ path
```

There is no test suite or linter configured.

## Architecture

Startup pipeline (`analyzer/cli.py`): load JSON → SQLite → compute analytics →
sync embeddings cache → print summary → REPL.

**Two stores, by design:**
- **In-memory SQLite** (`sqlite_store.py`) — the recursive `child_metrics` tree is
  flattened by `loader.py` into a `metrics` table; `analytics.py` writes a parallel
  `metric_analytics` table. Rebuilt every run.
- **PostgreSQL + pgvector** (`pg_cache.py`) — `metric_embeddings` is a *persistent*
  cache of embeddings for metric names, descriptions, and `element` values. Keyed by
  `sha256(kind, text)`, so each text is embedded once and the cache accumulates
  across runs and across domains. `PgCache` self-heals: it drops/recreates the table
  if the embedding dimension changes.

**Agent is strictly tools-only and two-stage** (`agent.py`, `tools.py`). The LLM
never writes SQL — it calls 11 typed `StructuredTool`s, each running a parameterized
query internally; there is no raw-SQL escape hatch.
- **Stage 1 (gathering)** — a LangChain 1.x `create_agent` runs the tool-calling
  loop. The system prompt is built per-dataset: exact dates, metric names, posts and
  `element` values are injected so the agent uses correct argument values.
- **Stage 2 (synthesis)** — `synthesize_answer` makes a separate call to the chat
  model *with no tools bound*, passing the question plus all gathered tool results
  as plain text. Its output is the answer shown to the user. If stage 1 used no
  tools (e.g. an out-of-scope question), its direct reply is used as-is.

**Two LLM providers.** The chat model switches via `LLM_PROVIDER` (`openai` |
`gigachat`) in `llm.py`. **Embeddings are always GigaChat**, regardless of the chat
provider — this fixes the pgvector dimension.

**Context budget.** GigaChat caps requests *that include functions* at ~4096 tokens
(its general context is 128k). Every step of the stage-1 tool loop carries the 11
tool schemas, so it must stay under 4096 — hence tool outputs are deliberately
compact (`tools.py`: curated fields, `None` stripped, numbers rounded; low row
limits in `sqlite_store.py`), `get_metric`/`compare` default to the aggregate
(`element IS NULL`) unless `element` is given, and the CLI keeps only
question/answer pairs in history. Stage 2 binds no functions, so it gets the full
128k. **When adding or changing tools, keep stage-1 outputs small.**

## Input JSON model

`{"me": <person>, "employees": [<person>...]}`. Each person has a recursive
`metrics` tree (`child_metrics`). Key per-metric semantics:
- `metric_type` — `прямая` (higher is better) or `обратная` (lower is better).
  All deviation/rank/trend logic must respect this direction.
- `element` — the breakdown dimension (a product/segment); `null` is the aggregate.
- `id` is **not** a unique key — it repeats across every `element` breakdown.

`analytics.py` is fully generic: direction comes from `metric_type`, peer groups are
`(metric_name, element, date)` — it never refers to specific metric names.

## Module map (`analyzer/`)

`loader` → flatten JSON · `sqlite_store` → SQLite schema + parameterized queries ·
`analytics` → derived `metric_analytics` + startup summary · `embeddings` → GigaChat
client · `pg_cache` → pgvector cache · `llm` → chat-model factory · `tools` → typed
agent tools · `agent` → tool-calling agent · `cli` → REPL entry point.
