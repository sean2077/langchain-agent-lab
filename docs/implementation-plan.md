# Implementation plan

### Slice `core-contract` — safe, validated research report contract
- **Status:** done
- **Blocked by:** none
- **Touches:** project scaffold, Pydantic domain types, citation validation, public-URL policy, unit tests
- **Test seam:** pure unit tests with no model or network
- **Verification:** `uv run --extra dev pytest tests/unit -q`
- **Result/Evidence:** `18 passed in 0.01s`

### Slice `agent-cli` — one core service works through a CLI
- **Status:** done
- **Blocked by:** core-contract
- **Touches:** model/search/page-reader ports, LangChain agent adapter, report assembler, CLI, fake-driven tests
- **Test seam:** deterministic fake model/tools plus explicit live integration markers
- **Verification:** `uv run --extra dev pytest tests/unit tests/integration/test_cli.py -q`
- **Result/Evidence:** `33 passed in 0.26s`; `uv run agent-learn --help` exits 0

### Slice `local-web-ui` — browser submits a question and renders a safe report
- **Status:** done
- **Blocked by:** agent-cli
- **Touches:** Streamlit app, progress/errors/source rendering, UI smoke test
- **Test seam:** Streamlit AppTest with injected deterministic service
- **Verification:** `uv run --extra dev pytest tests/ui -q`
- **Result/Evidence:** `2 passed in 0.67s`; Streamlit health endpoint returned `ok` on 127.0.0.1:8501

### Slice `learning-assets` — four ecosystem outcomes are runnable and documented
- **Status:** done
- **Blocked by:** core-contract
- **Touches:** LangChain/LangGraph/LangSmith/Deep Agents examples, ecosystem map, scenario exercise, README/resource guide
- **Test seam:** example import/smoke tests and documented expected outcomes
- **Verification:** `uv run --extra dev pytest tests/examples -q`
- **Result/Evidence:** `5 passed in 0.69s`; LangGraph interrupt/resume completed with `status=published`; Deep Agents live demo called `glossary_lookup` and returned its synthetic definition

### Slice `live-boundaries` — local model, web search and synthetic tracing are exercised
- **Status:** done (hosted LangSmith live trace awaits a user API key)
- **Blocked by:** agent-cli, local-web-ui, learning-assets
- **Touches:** Ollama setup checks, integration tests, synthetic LangSmith trace command, complete test suite
- **Test seam:** opt-in live tests against real local/external services
- **Verification:** `uv run --extra dev pytest -q` and `uv run --extra dev pytest -m live -q`
- **Result/Evidence:** Ollama 0.32.1 + `qwen3.5:9b`; final suite `61 passed, 1 skipped`; 5 non-hosted live boundaries passed; 5/5 quality cases returned grounded reports from successfully read sources; hosted LangSmith case is deterministically covered but live execution was skipped because `LANGSMITH_API_KEY` is not configured. This is historical 2026-07-18 structural evidence, not a current regression result or proof of semantic support; the reproducible workflow now lives in `agent-learn-eval` and `docs/quality-gate.md`.

### Slice `grounding-recovery` — recovered drafts stay quiet and Fake-IP DNS tolerates transient loss
- **Status:** done
- **Blocked by:** live-boundaries
- **Touches:** initial grounding prompt, one-pass repair diagnostics, deterministic answer cleanup, Fake-IP DoH transport/retry policy, live failure diagnostics, contract/concept docs
- **Test seam:** fake model drafts and repair responses; mocked DoH proxy configuration, transient failure, single-family success and bounded fail-closed cases; real local model and public pages
- **Verification:** `uv run --extra dev pytest -m "not live" -q`; `uv run --extra dev pytest -m "live and not hosted_langsmith" -q`; `uv run --extra dev ruff check .`; `uv run --extra dev ruff format --check .`; `uv lock --check`
- **Result/Evidence:** on 2026-07-22, deterministic suite `217 passed, 10 deselected`; non-hosted live suite `9 passed, 218 deselected`; the LangChain official page was read successfully three consecutive times after the DoH change. `agent-learn "LangChain v1 是什么？"` exited 0 without warnings, and `agent-learn --json "量子AI是什么"` returned `source_grounded` with an empty warning list. Hosted LangSmith was not run. These are runtime and structural results only; the Quantum AI report's mixed source quality still requires human semantic review.
