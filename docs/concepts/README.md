# 概念与边界问题

这里集中解释本项目最容易混淆、又会直接影响实现和验收的概念边界。每篇先回答问题，
再说明当前仓库如何实现、哪些结论不能从自动检查中推出，以及可以从哪里验证。

| 问题 | 一句话判断 | 详细答案 |
| --- | --- | --- |
| 搜索候选与已读证据有什么区别？为什么要重新验证最终 URL，并把标题与正文分开？ | 候选只是线索；只有安全读取后的最终页面才是证据，标题元数据也不应挤占正文预算。 | [来源候选、已读证据与最终 URL](source-provenance.md) |
| Citation identity、coverage 和 semantic support 分别证明什么？ | 前两者验证“引用指向谁、引用有没有覆盖正文”，语义支持才判断“来源是否真的支持陈述”。 | [引用保证的三个层级](citation-assurance.md) |
| Transport timeout、LangGraph recursion limit 与 wall-clock deadline 有什么区别？ | 它们分别约束 I/O 停顿、图 super-step 数和整次研究经过时间，不能相互冒充。 | [传输超时、图步骤与总时限](transport-timeouts.md) |
| 什么时候用直接 edge，什么时候用 conditional edge？ | 后继集合固定时直接连边；必须依据 state 选择路径时使用条件边。 | [LangGraph 的直接边与条件边](langgraph-edges.md) |
| 为什么正常运行强制关闭 hosted tracing，而 synthetic trace 可以开启？ | 正常请求可能含用户和网页内容，默认不得上传；固定合成 case 是显式、受限的外发实验。 | [Tracing 的隐私与启用边界](tracing-boundary.md) |

## 阅读方式

这些页面是解释性文档，规范仍以 [产品契约](../spec.md) 为准，操作验收仍以
[质量门槛](../quality-gate.md) 为准。代码变化后，如果页面中的“当前项目如何实现”与代码
冲突，应先修正文档或实现，再把新的验证证据记录到实施计划中。
