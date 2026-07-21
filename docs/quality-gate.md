# MVP 5 题质量门槛

这是一组固定、非敏感的本地 offline experiment。它把可确定性验证的结构属性与必须人工
判断的语义质量分开，不把 citation syntax 或 source identity 包装成事实正确性。

## 运行实验

前置条件：本地 Ollama 服务、已拉取配置模型、可访问所需官方网页。运行：

```bash
uv run agent-learn-eval
```

命令依次执行 5 个 case；某一题异常时继续其余题，最终仅在 5/5 自动检查全部通过时退出 0。
报告只输出到终端，不会启用 hosted tracing 或写入仓库。若要作为版本证据，应另行记录日期、
commit、模型和环境，并且不要提交模型输出或凭据。

## 自动 code evaluator

每题同时满足以下条件才自动通过：

1. 返回成功的 `ResearchReport`，其 citation identity、每个正文 block 的 citation coverage 和
   已读来源边界均通过核心契约；
2. case 指定的第一方页面出现在实际被引用的来源中，而不只是被搜索或读取。

指定页面 identity 精确比较 scheme、host、规范化尾斜杠后的 path 与 query；fragment 只是
客户端页内锚点，因此忽略。query 不同的资源必须在 case 中显式列为 accepted URL 才能通过。

自动检查不判断引用内容是否语义支持对应陈述，也不判断答案是否完整、清晰或可直接使用。

## 人工 rubric

逐题检查：

- 关键陈述是否能从对应 `[S#]` 页面得到语义支持；
- 比较性结论是否区分产品事实、厂商视角与分析推断；
- 是否回答了问题的全部部分，且没有明显矛盾或无关扩写；
- 是否无需重新研究即可直接使用。

| # | Case | 研究问题 | 自动结构门 | 人工语义支持 | 可直接使用 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `langchain-v1` | LangChain v1 的定位和标准 Agent API 是什么？ | 运行时输出 | ☐ | ☐ | LangChain v1 第一方文档 |
| 2 | `langgraph-selection` | 什么情况下应从 LangChain `create_agent` 下沉到 LangGraph？ | 运行时输出 | ☐ | ☐ | LangChain v1 + LangGraph overview |
| 3 | `langsmith-trace-eval` | LangSmith tracing 与 evaluation 分别解决什么问题？ | 运行时输出 | ☐ | ☐ | Observability + evaluation 第一方文档 |
| 4 | `deep-agents-harness` | Deep Agents 相比普通 LangChain Agent 增加了哪些 harness 能力？ | 运行时输出 | ☐ | ☐ | LangChain v1 + Deep Agents overview |
| 5 | `dify-positioning` | Dify 与 LangChain 的产品定位差异是什么？ | 运行时输出 | ☐ | ☐ | 双方第一方资料；厂商比较须标明视角 |

正式通过条件：当次自动结构门 5/5；人工语义支持逐题确认；“可直接使用”至少 4/5。

## 历史证据

`docs/implementation-plan.md` 记录 2026-07-18 曾得到 5/5 来源读取与 citation 结构结果，
但仓库没有保存该次逐题输出，也未记录人工语义评分。因此它只作为历史结构证据，不是当前
checkout 的回归结果，也不能替代本页的人工 rubric。
