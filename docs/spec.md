# LangChain 完整生态学习与本地资料研究 Agent

状态：approved

## Goal

使用 Python 3.12、LangChain v1 生态与本地 Ollama，在成果驱动的四阶段学习中掌握 LangChain、LangGraph、LangSmith 和 Deep Agents 的边界，并交付一个能生成可追溯 Markdown 报告的单用户本地 Web 资料研究助手。

## Product contract

- 只读搜索和网页读取；工具失败或证据不足时 fail closed，不用模型记忆补写事实。
- 核心接口为 `research(ResearchRequest) -> ResearchReport`。
- `ResearchRequest` 包含 `question`。
- `Source` 包含 `source_id`、`title`、`url`、`retrieved_at`，只在页面成功读取且最终 URL
  再次通过公网校验后创建；其元数据来自实际读取的最终页面，而不是搜索结果或登记时间。
- `ResearchReport` 包含 `answer_markdown`、稳定的 `outcome`、`sources`、`warnings`；
  `outcome` 区分 `source_grounded`、`agent_error`、`insufficient_evidence` 与
  `invalid_report`，`sources` 只列成功读取的页面，不包含未读搜索候选。
- Streamlit 使用参数化链接组件渲染来源，已验证 URL 不进入 Markdown destination 字符串。
- Streamlit warning/error 的 severity 文案固定，上游诊断详情只进入非 Markdown code element。
- CLI、Streamlit 与 eval 共享 domain outcome：只有 `source_grounded` 才标记成功，且 domain
  强制它包含有效 citations；fail-closed 报告保留答案与 warnings，但 CLI 返回非零、UI 标记
  未完成/error。
- CLI/eval 在 terminal sink 剔除 active C0/C1 controls（保留 tab/newline）；JSON sink 将残余
  controls 序列化为 `\uXXXX`，domain report 本身保持不变。
- CLI 在参数解析和 `ResearchRequest` 校验成功后才初始化运行时适配器；help 不依赖运行时
  配置。CLI、eval、synthetic trace 与 Streamlit 只把已分类的配置异常转换为无 traceback 的
  操作员错误；其他构造/执行异常保持可见，避免隐藏程序缺陷。
- 正文只允许引用已收集且成功读取来源的 `[S1]` 一类 source id；模型生成且会被 Streamlit 的
  GFM renderer 激活的链接目标不进入正文。内联/引用链接只保留 label，尖括号 autolink 与
  裸 HTTP(S)、`www.`、email、`mailto:`、`xmpp:` 目标会被移除；默认不启用 HTML rendering，
  该规则不声称提供通用 HTML sanitization。
- 每次 web search 在本地只登记并返回 provider 结果的前 5 条；该上限不依赖 provider 自行遵守，
  也不限制独立预登记的核验后官方候选。
- 成功报告至少包含一个 citable content block，且每个 prose paragraph、list item 和 table
  data row 都必须包含引用；Markdown heading、separator 和 fenced code block 属于结构性
  豁免。闭合或延伸到文末的 HTML comment 不可见，其中的标记不参与 citation identity 或
  coverage。该确定性规则验证 citation coverage 与 source identity，不声称验证引用内容在
  语义上支持对应陈述。
- 核心生态问题优先登记核验过的官方入口，但目录登记不等于可信引用，仍须通过相同公网读取边界。
- 本地质量实验使用 5 个固定、非敏感 case；code evaluator 只验证成功报告契约和指定第一方
  来源确实被引用；页面 identity 精确包含 scheme、host、path 与 query，忽略 fragment，且不
  将 identity 相等解释为语义支持。“可直接使用”仍由人工 rubric 评审。实验不启用 hosted
  tracing，不持久化模型输出。
- Streamlit 只绑定 `127.0.0.1`；CLI 调用同一个核心接口。
- LangSmith 只允许在专用合成测试配置中启用；正常 CLI/UI/eval 以 request-local context
  显式覆盖环境 tracing 开关，合成 opt-in 使用独立 project 和 `synthetic` tag。

## Technology decisions

- Python 3.12 + uv；LangChain/LangGraph v1 兼容依赖并提交 lockfile。
- Ollama `qwen3.5:9b` + `ChatOllama`；`OLLAMA_BASE_URL` 只允许 loopback HTTP(S)
  endpoint，并拒绝 URL credentials、query 与 fragment；Ollama client 不继承系统 HTTP
  proxy；`OLLAMA_TIMEOUT_SECONDS` 是正有限值，默认 300 秒，并作为 sync/async client 的
  connect/read/write/pool timeout；它不是 Agent run 的 wall-clock deadline。tool calling 或
  structured output smoke test 失败时停止并重新选型，不静默切云模型。
- 免费 DuckDuckGo Search；页面读取只允许公网 HTTP(S)，仅按精确主 media type 接受
  `text/html`、`text/plain`、`application/xhtml+xml`，拒绝本机/私网地址与其他内容，并限制
  重定向、超时和响应大小。读取器保留全部已验证地址，以解析结果的首地址族为偏好并保留同族
  相对顺序，交错 IPv4/IPv6 后顺序尝试；不做并发连接竞速。每次 `read()` 使用默认 30 秒的
  正有限连接尝试预算，由地址回退与重定向共享，并把每次新 HTTPX 请求的 timeout 压缩到
  剩余预算。该策略不硬中断同步 DNS 或持续进展的响应体读取，也不构成整页或 Agent run 的
  wall-clock deadline。
- Clash/Mihomo Fake-IP 仅触发公共 DNS 再验证；读取连接固定到验证后的公网 IP 并保留原域名 SNI/Host。
- Streamlit 本地单用户 UI；不做部署、认证、多用户或远程访问。

## Learning outcomes

- 画出 LangChain、LangGraph、LangSmith、Deep Agents 的关系图。
- 为 3 个场景选择正确层级并说明理由。
- 四个生态组件各运行一个最小示例。
- CLI 通过 3 个合成案例，并在 LangSmith 中解释 1 条合成 trace。
- 资料研究助手的 5 题自动结构门全部通过，且人工确认语义支持后至少 4 份可直接使用。

## Non-goals

- 不强制完成所有课程或获取证书。
- 不支持云模型、多模型、长期记忆、私人知识库 RAG 或外部写操作。
- 不强制最终 MVP 同时使用 LangGraph 与 Deep Agents；它们以独立示例验收。
- Dify、Eino、tRPC-Agent-Go、Coze Studio 与 LangChainGo 仅作生态对照。
