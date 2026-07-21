# 引用保证的三个层级

## 问题

Citation identity、citation coverage 和 semantic support 分别证明什么？哪些事情是前两者
无法证明的？

## 简短答案

- **Citation identity** 证明 `[S1]` 能映射到本次请求中一个已成功读取的具体来源。
- **Citation coverage** 证明要求引用的每个正文 block 至少出现一个合法 `[S#]`。
- **Semantic support** 判断该来源内容是否真的支持它旁边的陈述。

前两项是确定性的结构检查；第三项是内容判断。一个答案可以拥有完美的引用格式和覆盖率，
同时把来源的结论说反。

## 三层保证分别回答什么

| 层级 | 回答的问题 | 本项目如何判定 | 通过后仍然未知 |
| --- | --- | --- | --- |
| Identity | “这个标记指向哪个来源？” | 标记必须为规范 `[S#]`；ID 必须已登记、已读取，并存在于报告 `sources` | 来源是否支持陈述、来源质量、陈述是否完整 |
| Coverage | “哪些正文块没有任何引用？” | 每个 prose paragraph、list item、table data row 至少含一个合法标记 | 标记是否放在正确陈述旁、引用是否支持整块内容 |
| Semantic support | “来源内容是否蕴含或合理支撑陈述？” | 当前由人工 rubric 对照来源与陈述判断 | 仍可能需要判断来源权威性、时效性和多来源冲突 |

### Identity 在项目中有两层含义

运行时 identity 是 `[S#] -> Source` 的映射。`ResearchService` 先拒绝虚构 ID，再拒绝只搜索
但未读取的 ID；`ResearchReport` 还要求引用 ID 存在于它实际携带的 `sources` 中。

质量实验另有“指定页面 identity”：它比较 URL 的 scheme、host、规范化尾斜杠后的 path 和
精确 query，并忽略 fragment。这只能证明报告引用了 case 接受的资源地址，不能证明页面中的
具体段落支持答案。

### Coverage 是语法覆盖，不是事实覆盖

本项目把以下内容视为需要引用的 block：

- 普通正文段落；
- 每个列表项，包括嵌套列表项；
- Markdown 表格的每个数据行。

标题、分隔线和 fenced code block 是结构性内容，因此豁免。成功报告必须至少存在一个可引用
正文 block；只把 `[S1]` 放进标题或代码块也不能通过。

HTML comment 不会渲染为读者可见内容，因此其中的 `[S1]` 也不能提供 identity 或 coverage。
闭合 comment 与从 `<!--` 延伸到文末的未闭合 comment 都从 citation 分析中排除；否则一段
没有可见标记的正文会被误判为已有来源。

Coverage 的检查单位是 Markdown 结构，不会解析一句话中包含几个独立事实。例如：

```markdown
LangGraph 是数据库，并且只能使用云模型。[S1]
```

只要 `S1` 是已读来源，这一段可以同时通过 identity 和 coverage；但两项陈述都可能与来源
内容无关或相反，因此 semantic support 仍然失败。

## 前两层明确不能证明什么

Identity 与 coverage 不能单独证明：

- 引用页面真的表达了对应结论；
- 模型没有误读、夸大、偷换条件或把相关性写成因果性；
- 答案覆盖了问题的所有部分；
- 来源是权威、最新、中立或彼此一致的；
- 比较性结论已区分产品事实、厂商立场和分析推断；
- 答案已经达到“无需重新研究即可直接使用”。

它们也不等同于事实正确性。Semantic support 可以发现“来源没有支持这句话”，但即使来源
支持，来源本身也可能过时或错误，因此高风险结论还需要来源质量与交叉核验。

## 为什么仍然值得自动检查 identity 与 coverage

结构门不能解决语义问题，但能便宜、稳定地排除两类基础失败：

1. `[S9]` 根本不存在，或模型只看过搜索摘要却引用未读 `S1`；
2. 答案只有最后一段带引用，其余正文完全没有 provenance。

把这些机械问题挡在前面，人工评审就可以集中在“来源是否支持陈述”而不是逐个检查引用 ID
是否合法。项目因此采用分层验收：自动结构门通过之后，仍明确要求人工 semantic support
与直接可用性审阅。

## 人工 semantic support 的最小检查

对每个有实质内容的陈述：

1. 找到紧邻的 `[S#]`；
2. 打开报告单独渲染的来源 URL；
3. 在页面中定位能支持该陈述的段落、表格或 API 定义；
4. 检查限定条件、版本、主语和比较范围是否被答案保留；
5. 若只能得到部分支持，就缩小陈述或补充来源，不能用“已有引用”代替判断。

## 当前实现与测试入口

- [`domain.py`](../../src/agent_learn/domain.py)：规范引用、正文 block 划分、identity 与 coverage 契约。
- [`research.py`](../../src/agent_learn/research.py)：拒绝未知或未读 source ID，并构造 fail-closed 结果。
- [`evaluation.py`](../../src/agent_learn/evaluation.py)：固定 case 的指定页面 identity 检查。
- [`quality-gate.md`](../quality-gate.md)：自动结构门与人工 semantic support rubric。
- [`test_domain.py`](../../tests/unit/test_domain.py)：段落、列表、表格和结构性豁免的确定性用例。
- [`test_research.py`](../../tests/unit/test_research.py)：虚构、未读和覆盖不完整引用的失败路径。
