# langchain-agent-lab

一个使用 LangChain v1、Ollama 与 Streamlit 构建的本地、只读、来源可追溯的资料研究 Agent，同时包含 LangGraph、LangSmith 与 Deep Agents 的成果驱动学习示例。

## 能力边界

- 模型在本机 Ollama 运行，默认 `qwen3.5:9b`；`OLLAMA_BASE_URL` 只接受
  `localhost`、IPv4 loopback 或 IPv6 loopback 的 HTTP(S) endpoint，其他目标会在启动时拒绝；
  Ollama client 不继承系统 HTTP proxy。transport 的 connect/read/write/pool timeout 默认
  为 300 秒，可通过正有限值 `OLLAMA_TIMEOUT_SECONDS` 调整；研究主路径把传输超时纳入
  既有 fail-closed，但这不是整个 Agent run 的硬 wall-clock deadline。
- Agent 只能搜索公网和读取已登记的候选，不能把任意 URL 直接交给读取工具。搜索候选与
  已读证据分开保存；报告只列出成功读取的页面，并使用重定向后再次通过公网校验的最终
  URL、页面标题和实际读取时间，不会把未读候选伪装成来源。每次 web search 最多把 provider
  返回的前 5 条结果登记并交给模型，即使 provider 忽略请求的结果上限。
- Streamlit 来源链接通过分离的 label/URL 参数渲染，来源 URL 不会拼接进 Markdown 语法；
  远端页面标题进入 GFM-capable label 前会移除活动链接、图片和 autolink 目标，报告中的原始
  provenance 标题保持不变。
- Streamlit warning/error 使用固定 alert 文案，并把上游诊断详情作为非 Markdown code text
  渲染，避免把搜索结果或异常内容解释成活动链接。
- `ResearchReport.outcome` 提供稳定的 terminal category；domain 只允许带有效 citations 的
  `source_grounded` 结果，CLI/UI/eval 共享该判断。fail-closed 报告在 CLI 返回非零、在
  Streamlit 显示未完成/error，并保留答案与详细 warnings。
- CLI/eval 的 plain stdout/stderr 会剔除 ANSI/C0/C1 terminal controls（保留 tab/newline）；JSON
  将残余控制字符转成标准 `\uXXXX` escape，不修改存储在 `ResearchReport` 中的数据。
- CLI 在初始化运行时适配器前完成参数解析和问题校验；`--help` 不依赖 Ollama 配置。已分类的
  运行时配置错误在 CLI、eval 与 synthetic trace 返回退出码 2 和简短错误，在 Streamlit
  显示固定错误与非 Markdown 详情；普通编程异常不会被宽泛捕获并伪装成配置错误。
- 成功报告必须至少包含一个可引用正文 block，且每个正文段落、列表项和表格数据行都必须
  包含 `[S1]` 形式引用；标题、分隔线和 fenced code block 属于结构性豁免。未知、未成功
  读取或覆盖不完整的来源 id 会导致 fail-closed 报告；该检查证明引用可见且来源已读取，
  不等同于语义蕴含证明。
- LangChain 生态问题会先登记仓库内核验过的官方入口，但仍须真实读取成功后才能引用。
- 模型生成且会被 GFM 激活的链接目标不会进入正文：内联/引用链接只保留 label，autolink 与
  裸 URL/email 目标会移除；HTML rendering 保持关闭。常见 citation 格式偏差会规范化，
  必要时最多做一次无工具修订。
- Clash/Mihomo Fake-IP 场景使用公共 DNS 再验证并固定到公网 IP，不直接放行 `198.18.0.0/15`。
- 页面读取保留全部已验证公网地址；以解析结果的首地址族为偏好、保留同族相对顺序，交错
  IPv4/IPv6 后再顺序尝试。一次 `read()` 默认使用 30 秒的正有限连接尝试预算，由所有地址和
  重定向共享。每次新请求的 HTTPX timeout 会压缩到剩余预算，预算耗尽即 fail closed。该
  顺序策略不是并发竞速；预算不能硬中断同步 DNS 或持续有数据到达的响应体处理，也不是整页
  读取或整个 Agent run 的硬 wall-clock deadline。
- 页面响应只精确允许 `text/html`、`text/plain` 与 `application/xhtml+xml` 主 media type；
  header 参数中出现这些字符串不会绕过非网页内容拒绝。
- Streamlit 只监听 `127.0.0.1`，没有认证、多用户和公开部署。
- 正常 CLI/UI/eval 显式覆盖环境 tracing 开关并强制关闭托管 tracing；只有固定合成 case
  可以启用带 `synthetic` tag 的 LangSmith context。

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

## 本地质量实验

启动 Ollama 并确保可以访问公网后，运行固定的 5-case dataset：

```bash
uv run agent-learn-eval
```

命令逐题输出报告供人工审阅，并用确定性 code evaluator 检查报告契约和指定第一方来源是否
真的被引用；单题失败不会中止其余 case。它不会启用 hosted tracing，也不会保存模型输出。
语义支持与“可直接使用”仍必须按 [`docs/quality-gate.md`](docs/quality-gate.md) 人工判断。

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
- [`docs/concepts/README.md`](docs/concepts/README.md)：来源、引用、超时、LangGraph edge 与 tracing 隐私边界的 5 组详细问答。
- [`docs/quality-gate.md`](docs/quality-gate.md)：5 个真实问题的可重复实验、自动检查与人工 rubric。
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

其中 5 个质量 case 也可单独收集或运行：

```bash
uv run --extra dev pytest tests/live/test_live_boundaries.py -k end_to_end_quality_case -q
```

## 已知限制

- Hosted LangSmith trace 必须由用户提供有效 `LANGSMITH_API_KEY`；没有 key 时明确退出或跳过。
- 页面读取为防 DNS 重绑定而直连并固定到已验证公网 IP；支持本机 Mihomo/Clash TUN Fake-IP，但仅允许显式 HTTP proxy、禁止直连公网的网络会 fail closed。
- 仓库只记录了 2026-07-18 的历史 5/5 结构证据，不将其视为当前回归；每个 checkout
  仍需重跑 `agent-learn-eval`，人工语义支持与“可直接使用”结论须按质量门槛逐题记录。

## 代码结构

- `domain.py`：稳定的请求、来源和报告契约。
- `research.py`：一次研究请求的深模块与 fail-closed 策略。
- `tools.py`：每次请求独立地管理搜索候选与已读证据，只允许按已登记的 source id 读取。
- `catalog.py`：LangChain、LangGraph、LangSmith、Deep Agents 与 Dify 的核验后官方入口。
- `security.py`：公网 URL、DNS、Fake-IP 与 SSRF 防护边界。
- `adapters.py`：DuckDuckGo、受限 HTTP reader、LangChain 与 Ollama 适配器。
- `cli.py` / `ui.py`：共享同一核心服务的两个界面。
