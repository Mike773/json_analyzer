# json_analyzer

Universal metrics-analyst agent. Ingests a fixed-shape JSON document of
hierarchical metrics, loads it into in-memory SQLite, enriches it with derived
analytics, and answers questions through an interactive CLI chat. Call-center
metrics in `samples/test_metrics.json` are just one example — the same code
handles metrics for developers, managers, executives, etc. Nothing hardcodes
specific metric names.

## Quickstart

```bash
# 1. Python 3.12 venv (langchain 1.x needs 3.10+)
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/pip install -e .

# 2. PostgreSQL with pgvector (embeddings cache)
docker compose up -d

# 3. Configure providers and credentials
cp .env.example .env
# edit .env: LLM_PROVIDER=openai|gigachat, model name, API keys, POSTGRES_DSN

# 4. Run the analyst (defaults to samples/test_metrics.json)
.venv/bin/python -m analyzer.cli [path-to-json]
```

Type `?` in the REPL to reprint the suggested questions.

## Repo layout

- `analyzer/` — the agent itself (loader, SQLite store, analytics, tools, agent, CLI).
- `samples/` — example metric datasets, including raw-format converters.
- `gen_metrics.py`, `gen_metrics_agile.py`, `convert_raw.py` — data generators / converters.
- `eval_run.py`, `eval_value.py`, `eval_out/`, `eval_value_out/`, `eval_report.md`,
  `eval_value_report.md` — evaluation harness and recorded runs.

## Deeper docs

- `CLAUDE.md` — architecture, two-store design, context budget, module map.
- `metrics_pipeline.md` — startup pipeline and per-metric calculation algorithms.
- `agent_tools.md` — the 11 typed tools the agent uses.
- `scenarios_employee.md`, `scenarios_manager.md` — example user scenarios.
