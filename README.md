# langchain-agent-lab

一个使用 LangChain v1、Ollama 与 Streamlit 构建的本地、只读、来源可追溯的资料研究 Agent，同时包含 LangGraph、LangSmith 与 Deep Agents 的成果驱动学习示例。

## 能力边界

- 模型在本机 Ollama 运行，默认 `qwen3.5:9b`；`OLLAMA_BASE_URL` 只接受
  `localhost`、IPv4 loopback 或 IPv6 loopback 的 HTTP(S) endpoint，其他目标会在启动时拒绝；
  Ollama client 不继承系统 HTTP proxy。
- Agent 只能搜索公网和读取已登记的候选，不能把任意 URL 直接交给读取工具。搜索候选与
  已读证据分开保存；报告只列出成功读取的页面，并使用重定向后再次通过公网校验的最终
  URL、页面标题和实际读取时间，不会把未读候选伪装成来源。
- 成功报告必须至少包含一个可引用正文 block，且每个正文段落、列表项和表格数据行都必须
  包含 `[S1]` 形式引用；标题、分隔线和 fenced code block 属于结构性豁免。未知、未成功
  读取或覆盖不完整的来源 id 会导致 fail-closed 报告；该检查证明引用可见且来源已读取，
  不等同于语义蕴含证明。
- LangChain 生态问题会先登记仓库内核验过的官方入口，但仍须真实读取成功后才能引用。
- 模型生成的链接目标不会进入正文；常见 citation 格式偏差会规范化，必要时最多做一次无工具修订。
- Clash/Mihomo Fake-IP 场景使用公共 DNS 再验证并固定到公网 IP，不直接放行 `198.18.0.0/15`。
- Streamlit 只监听 `127.0.0.1`，没有认证、多用户和公开部署。
- 正常 CLI/UI 强制关闭托管 tracing；只有固定合成 case 可以启用 LangSmith。

## 快速开始

前置条件：Python 3.12、[uv](https://docs.astral.sh/uv/) 和 [Ollama](https://ollama.com/download/linux)。

```bash
ollama serve
```

如果 Ollama 已由系统服务启动，可跳过上一步。然后在另一个终端执行：

```bash
ollama pull qwen3.5:9b
uv sync --extra dev
```

运行 CLI：

```bash
uv run agent-learn "LangChain v1 是什么？"
```

运行仅绑定本机的 Web UI：

```bash
uv run streamlit run streamlit_app.py \
  --server.address=127.0.0.1 \
  --server.port=8501 \
  --server.headless=true
```

打开 <http://127.0.0.1:8501>。

## 合成 LangSmith trace

trace 命令不接收任意问题，只允许三个仓库内固定的非敏感 case：

```bash
export LANGSMITH_API_KEY="..."
uv run agent-learn-trace --case langchain-overview
```

可用 case：`langchain-overview`、`tool-selection`、`local-agent`。正常 UI 不读取这个开关来启用 tracing。

## 学习示例

```bash
uv run python examples/langchain_agent.py
uv run python examples/langgraph_workflow.py
uv run python examples/deep_agent.py
uv run python examples/langsmith_trace.py --case tool-selection
```

- [`docs/ecosystem-map.md`](docs/ecosystem-map.md)：LangChain、LangGraph、LangSmith、Deep Agents、Dify 与 Go 生态定位。
- [`docs/learning-path.md`](docs/learning-path.md)：四阶段路线、官方资源和三个选型场景。
- [`docs/quality-gate.md`](docs/quality-gate.md)：5 个真实问题的自动验收记录与用户确认栏。
- [`docs/spec.md`](docs/spec.md)：批准后的产品契约与非目标。

## 验证

确定性测试不会访问模型或网络：

```bash
uv run --extra dev pytest -m "not live" -q
uv run --extra dev ruff check .
```

[`ci.yml`](.github/workflows/ci.yml) 会在 push 和 pull request 上使用锁定依赖运行相同的
non-live 测试、lint 与 format check。CI 不运行需要 Ollama、公网或 LangSmith key 的 live 边界。

真实边界测试需要本地 Ollama；LangSmith 测试还需要 `LANGSMITH_API_KEY`：

```bash
uv run --extra dev pytest -m live -q
```

只运行本地模型与公网边界（不选择 hosted LangSmith）：

```bash
uv run --extra dev pytest -m "live and not hosted_langsmith" -q
```

## 已知限制

- Hosted LangSmith trace 必须由用户提供有效 `LANGSMITH_API_KEY`；没有 key 时明确退出或跳过。
- 页面读取为防 DNS 重绑定而直连并固定到已验证公网 IP；支持本机 Mihomo/Clash TUN Fake-IP，但仅允许显式 HTTP proxy、禁止直连公网的网络会 fail closed。
- 5 题自动来源与引用检查已完成；“可直接使用”仍由用户在质量门槛文档中确认。

## 代码结构

- `domain.py`：稳定的请求、来源和报告契约。
- `research.py`：一次研究请求的深模块与 fail-closed 策略。
- `tools.py`：每次请求独立地管理搜索候选与已读证据，只允许按已登记的 source id 读取。
- `catalog.py`：LangChain、LangGraph、LangSmith、Deep Agents 与 Dify 的核验后官方入口。
- `security.py`：公网 URL、DNS、Fake-IP 与 SSRF 防护边界。
- `adapters.py`：DuckDuckGo、受限 HTTP reader、LangChain 与 Ollama 适配器。
- `cli.py` / `ui.py`：共享同一核心服务的两个界面。
