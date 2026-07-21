# Tracing 的隐私与启用边界

## 问题

为什么正常 CLI/UI/eval 即使环境变量开启了 LangSmith tracing，也要在 request-local context
中强制关闭？Synthetic trace 又为什么可以例外开启？

## 简短答案

Hosted tracing 是一次对外网络写入，可能携带问题、模型消息、工具输入输出、网页正文和错误
详情。正常研究接受任意用户问题，因此项目的 local-first 隐私契约要求默认且强制不上传。
固定 synthetic case 则由用户通过专用命令显式选择，输入范围受控，并进入独立 project 且带
`synthetic` tag，所以可以作为有边界的可观测性实验开启。

例外的理由不是“trace 天生安全”，而是这条路径具有明确目的、显式同意和更小的数据范围。

## 为什么不能只依赖环境默认值

`LANGSMITH_TRACING=true` 可能来自用户 shell、IDE、父进程或另一项本机实验。若正常入口只是
“没有主动开启 tracing”，库仍可能继承这个进程级配置并上传本次调用。

项目因此在真正包围 agent/model 调用的位置使用：

```python
with tracing_context(enabled=False):
    ...
```

`LangChainAgentBackend` 实际把 `enabled` 绑定到显式的 `trace_enabled` 参数。正常路径传入
`False`，因此即使进程环境全局为 true，agent 调用和后续引用修订调用仍在关闭 context 内。

Request-local context 相比临时修改环境变量有三个优势：

- 范围只覆盖当前调用，不改变整个进程的配置；
- 退出 context 后恢复外层状态；
- 并发或嵌套调用不需要争用同一个可变的进程环境开关。

测试专门构造了“环境全局开启”的情况，验证正常 agent 与 repair 调用观察到的 tracing 都是
关闭状态，并且 context 结束后外层开启状态得到恢复。

## 哪些入口属于正常运行

| 入口 | 接受的数据 | 组合方式 | Hosted tracing |
| --- | --- | --- | --- |
| `agent-learn` CLI | 任意用户问题 | `build_research_service(trace_enabled=False)` | 强制关闭 |
| Streamlit UI | 任意用户问题 | `build_research_service(trace_enabled=False)` | 强制关闭 |
| `agent-learn-eval` | 仓库固定 5 题，但输出用于本地质量评审 | `build_research_service(trace_enabled=False)` | 强制关闭 |

Eval 即使使用固定问题也不是 trace demo。它的职责是本地质量门，不能因为环境里恰好存在
LangSmith 配置就产生外部副作用。

## Synthetic trace 为什么可以开启

专用 `agent-learn-trace` 路径同时具备以下限制：

1. 用户必须显式运行 trace 命令并选择一个允许的 `--case`；
2. 命令不接受任意问题，只接受仓库内固定的非敏感 case；
3. 没有 `LANGSMITH_API_KEY` 时明确退出；
4. 服务以 `trace_enabled=True` 构造；
5. context 使用独立 `LANGSMITH_PROJECT`，并附加 `synthetic` tag。

这些约束让 trace 容易识别和筛选，也避免把普通用户输入意外混进 hosted 项目。固定问题
只降低输入敏感度，并不意味着 trace 内容为空：agent 运行期间检索到的公开网页内容、工具结果
和模型输出仍可能进入 trace。运行者仍应把该命令视为明确的外发操作。

## 边界矩阵

| 条件 | 正常 CLI/UI/eval | Synthetic trace |
| --- | --- | --- |
| 用户显式选择上传 | 否 | 是 |
| 问题是否任意 | 是 | 否，仅固定 case |
| 环境全局 tracing 能否改变行为 | 不能 | 仍由专用入口显式开启 |
| Hosted project/tag | 不设置 | 独立 project + `synthetic` |
| 缺少 API key | 不影响本地运行 | 明确退出 |

因此“环境变量存在”不是授权；专用入口、固定数据和显式调用共同构成授权边界。

## 当前实现与测试入口

- [`adapters.py`](../../src/agent_learn/adapters.py)：包围 agent 与 repair 的 request-local
  `tracing_context`。
- [`cli.py`](../../src/agent_learn/cli.py)、[`ui.py`](../../src/agent_learn/ui.py) 和
  [`evaluation.py`](../../src/agent_learn/evaluation.py)：正常入口显式传入 `False`。
- [`trace_demo.py`](../../src/agent_learn/trace_demo.py)：固定 case、API key gate 和显式 opt-in。
- [`test_adapters.py`](../../tests/unit/test_adapters.py)：环境覆盖、状态恢复、project 与 tag 的
  确定性测试。
