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
- `ResearchReport` 包含 `answer_markdown`、`sources`、`warnings`；`sources` 只列成功读取
  的页面，不包含未读搜索候选。
- Streamlit 使用参数化链接组件渲染来源，已验证 URL 不进入 Markdown destination 字符串。
- 正文只允许引用已收集且成功读取来源的 `[S1]` 一类 source id；模型生成的链接目标不进入正文。
- 成功报告至少包含一个 citable content block，且每个 prose paragraph、list item 和 table
  data row 都必须包含引用；Markdown heading、separator 和 fenced code block 属于结构性
  豁免。该确定性规则验证 citation coverage 与 source identity，不声称验证引用内容在语义上
  支持对应陈述。
- 核心生态问题优先登记核验过的官方入口，但目录登记不等于可信引用，仍须通过相同公网读取边界。
- 本地质量实验使用 5 个固定、非敏感 case；code evaluator 只验证成功报告契约和指定第一方
  来源确实被引用，语义支持与“可直接使用”由人工 rubric 评审。实验不启用 hosted tracing，
  不持久化模型输出。
- Streamlit 只绑定 `127.0.0.1`；CLI 调用同一个核心接口。
- LangSmith 只允许在专用合成测试配置中启用，正常 UI 默认关闭。

## Technology decisions

- Python 3.12 + uv；LangChain/LangGraph v1 兼容依赖并提交 lockfile。
- Ollama `qwen3.5:9b` + `ChatOllama`；`OLLAMA_BASE_URL` 只允许 loopback HTTP(S)
  endpoint，并拒绝 URL credentials、query 与 fragment；Ollama client 不继承系统 HTTP
  proxy；tool calling 或 structured output smoke test 失败时停止并重新选型，不静默切云模型。
- 免费 DuckDuckGo Search；页面读取只允许公网 HTTP(S)，拒绝本机/私网地址与非网页内容，并限制重定向、超时和响应大小。
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
