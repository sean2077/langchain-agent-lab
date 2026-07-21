# 成果驱动学习路线

默认节奏为 4 周、每周 5–7 小时。课程是参考材料；是否进入下一阶段由产出决定。

## 阶段 1：LangChain v1 与 CLI

- 阅读 [LangChain v1](https://docs.langchain.com/oss/python/releases/langchain-v1) 与 [Quickstart](https://docs.langchain.com/oss/python/langchain/quickstart)。
- 完成 [LangChain Essentials - Python](https://academy.langchain.com/courses/langchain-essentials-python) 中与模型、工具、structured output、memory 相关的内容。
- 运行 `examples/langchain_agent.py` 与项目 CLI；通过 3 个合成案例。

## 阶段 2：LangGraph、LangSmith 与 Deep Agents

- 运行 `examples/langgraph_workflow.py`，观察 interrupt 前后的 checkpoint state。
- 学习 [LangGraph Essentials](https://academy.langchain.com/courses/langgraph-essentials-python)。
- 运行固定合成 case 的 `agent-learn-trace`，在 LangSmith 中解释模型、工具和终止节点。
- 运行 `examples/deep_agent.py`，对比普通 `create_agent` 与 Agent harness。

## 阶段 3：只读资料研究核心

- 理解搜索候选与已读证据的 provenance 边界、`[S1]` identity/coverage 引用契约、语义支持
  边界和 fail-closed 行为。
- 运行单元测试，分别让搜索、页面读取、模型与引用校验失败一次。
- 用 CLI 完成三个非敏感问题，并检查来源是否支持正文。

## 阶段 4：本地 Web UI 与 5 题验收

- 在 `127.0.0.1` 启动 Streamlit。
- 运行 `uv run agent-learn-eval`，理解固定 dataset、code evaluator 与一次 experiment 的边界。
- 确认 5 题自动结构门全部通过；自动结果不等同于引用对陈述的语义支持。
- 按 `docs/quality-gate.md` 人工核对语义支持，至少 4 份报告达到“无需重新研究即可直接使用”。

## 三个场景选型题

### 场景 1：天气与计算工具助手

选择 LangChain `create_agent`：任务是标准工具循环，没有复杂持久状态。

### 场景 2：需要审批、暂停和恢复的长时工作流

选择 LangGraph：明确需要 state、conditional edge、checkpoint 与 interrupt/resume。

### 场景 3：需要规划、文件系统和子 Agent 的开放式研究任务

选择 Deep Agents，并用 LangSmith 做 trace/evaluation；LangGraph 作为底层运行时，不必手写所有节点。

## 官方资源

- [LangChain Python Quickstart](https://docs.langchain.com/oss/python/langchain/quickstart)
- [LangChain Essentials](https://academy.langchain.com/courses/langchain-essentials-python)
- [LangGraph v1](https://docs.langchain.com/oss/python/releases/langgraph-v1)
- [LangGraph Overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangGraph Essentials](https://academy.langchain.com/courses/langgraph-essentials-python)
- [LangSmith Observability](https://docs.langchain.com/langsmith/observability-concepts)
- [LangSmith Evaluation](https://docs.langchain.com/langsmith/evaluation)
- [LangSmith Essentials](https://academy.langchain.com/courses/quickstart-langsmith-essentials)
- [Deep Agents Overview](https://docs.langchain.com/oss/python/deepagents/overview)
- [Introduction to Deep Agents](https://academy.langchain.com/courses/foundation-introduction-to-deepagents)
