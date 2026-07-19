# LangChain Agent Lab — Agent Contract

## Project overview

This is a Python 3.12 learning lab and local research agent built with LangChain v1,
LangGraph, LangSmith, Deep Agents, Ollama, and Streamlit. Read `README.md` for the
operator workflow and `docs/spec.md` for the product contract.

## Development commands

```bash
uv sync --extra dev
uv run --extra dev pytest -m "not live" -q
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run agent-learn "LangChain v1 是什么？"
```

Run live tests only when their Ollama, network, and optional LangSmith prerequisites
are available; never treat a skipped hosted boundary as verified.

## Architecture and invariants

- `src/agent_learn/domain.py` owns stable request, source, and report contracts.
- `src/agent_learn/research.py` orchestrates one research request and fail-closed output.
- `src/agent_learn/tools.py` owns the per-request source registry; pages are read by
  registered source ID, never by an arbitrary model-supplied URL.
- `src/agent_learn/security.py` and `adapters.py` enforce public-network, DNS, Fake-IP,
  SSRF, and external-service boundaries. Preserve those checks at every adapter seam.
- CLI and Streamlit share the same core service. Normal CLI/UI execution must keep
  hosted tracing disabled; only fixed synthetic cases may enable LangSmith tracing.
- Never commit `.env`, Streamlit secrets, credentials, model output, or local runtime
  state. Keep citations source-grounded and fail closed on unreadable or unknown sources.

<!-- agent-scaffold:start — managed by the agent-scaffold skill. Edit project prose OUTSIDE these markers; `agent-scaffold upgrade` refreshes this block. -->
## Agent Harness (Claude Code + Codex)

This repo carries a vendored, dual-host agent harness. `.agents/` is the single
source of truth (SSOT); `.claude/` and `.codex/` are wired to the **same**
implementations under `.agents/tools/`.

### Worktree-per-change (hard rule)

**Never edit trunk (`main`) directly** — every change, however small ("just docs"
is NOT an exception), starts in its own worktree cut from the trunk tip:

```bash
bash .agents/tools/worktree.sh new <name>   # edit inside .worktrees/<name>/  (branch feat|fix|docs|chore/<name>)
bash .agents/tools/worktree.sh done         # merge back to local trunk (--no-ff) + clean up + ff-only push
```

`.agents/tools/hooks/trunk_edit_guard.sh` (PreToolUse) mechanically blocks edits to
tracked files while on trunk. Escape hatch — only when the user explicitly
authorizes a trunk edit: `touch .claude/allow-trunk-edit` (auto-expires in 2 h)
or `WORKTREE_ALLOW_TRUNK_EDIT=1`.

### Authority docs

`AGENTS.md` (root plus nested contracts created only for local differences;
root `CLAUDE.md` is a symlink to it) is an **entry
point**, not a detail dump. `.agents/tools/hooks/authority_doc_budget.sh`
(PostToolUse) advises when a contract exceeds its line budget (root 320 / nested
120; override with `AUTHORITY_DOC_MAX_ROOT|NESTED`). Nested contracts carry a
`<!-- Parent: ... -->` link to the nearest existing ancestor contract.

### SSOT layout

| Path | Role | Commit? |
|---|---|---|
| `.agents/skills/<name>/SKILL.md` | project skill source | ✅ |
| `.agents/subagents/<name>/{metadata.json,instructions.md}` | subagent source | ✅ |
| `.claude/skills/<name>` | symlink → `.agents/skills/<name>` (CC discovery; Codex reads `.agents/` directly) | ✅ |
| `.claude/agents/*.md`, `.codex/agents/*.toml` | **generated** subagent projections — do NOT hand-edit | ✅ |
| `.agents/tools/hooks/` | scaffold-managed hook runtime (doc budget + optional trunk guard) | ✅ |
| `.agents/tools/worktree.sh` | worktree lifecycle | ✅ |
| `.claude/allow-trunk-edit` | worktree escape hatch | ❌ ignored |
| `.claude/settings.local.json` | personal overrides | ❌ ignored |

- **Add a skill**: edit `.agents/skills/` → run `bash .agents/relink-skills.sh` → commit source + symlink.
- **Add a subagent** (needs python): edit `.agents/subagents/` → run `python .agents/tools/generate-subagents.py` → commit source + generated. Wire `--check` into the project's own CI or hook manager when desired.
- **Third-party skills** follow project-owned placement and installation policy. The relinker manages only names sourced from `.agents/skills/`, preserves unrelated entries, and fails on same-name ownership conflicts.

**Codex trust**: project-level `.codex/` (config + hooks + agents) only loads for a
**trusted** project; until trusted it is silently skipped. Trust once: run `codex`
here and accept, or add `[projects."<repo abs path>"] trust_level = "trusted"` to
`~/.codex/config.toml`.
<!-- agent-scaffold:end -->
