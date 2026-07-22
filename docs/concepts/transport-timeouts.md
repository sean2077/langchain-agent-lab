# 传输超时、图执行与总时限

## 问题

HTTPX 的 connect/read/write/pool transport timeout、LangGraph recursion/concurrency limit，
与整个 Agent run 的 wall-clock deadline 有什么区别？

## 简短答案

Transport timeout 限制一次 HTTP 操作在某个 I/O 阶段最多等待多久；wall-clock deadline
限制整次 `research(...)` 从开始到结束最多经过多久。前者能防止一个连接阶段永久停住，但
不会自动约束多次模型调用、工具调用、重定向和修订调用累计起来的总时长。LangGraph
recursion limit 限制一次图执行的 super-step 深度，`max_concurrency` 限制同一时刻的任务宽度；
两者都不计量秒数。

## 四种 transport timeout

| 类型 | 限制的等待 | 典型停顿 |
| --- | --- | --- |
| connect | 建立一个网络连接最多等待多久 | 目标不可达、握手迟迟不能完成 |
| read | 从已连接的对端等待下一段响应数据最多多久 | 服务已连接但长时间不返回下一个 chunk |
| write | 向对端发送下一段请求数据最多等待多久 | 对端不继续接收请求体 |
| pool | 从连接池取得可用连接最多等待多久 | 并发请求占满连接池 |

HTTPX 接收一个标量 `timeout=300` 时，会把该值用作这四类 timeout 的默认值。它们通常是
“当前阶段允许连续等待多久”，不是“整个 HTTP request 从第一字节到最后一字节只能运行多久”。
例如服务每隔 9 秒返回一个 chunk，`read=10` 可以一直不超时，但总下载时间仍可能超过 10 秒。

## 为什么它不等于 Agent 的 wall-clock deadline

一次研究可能依次发生：

1. 模型决定调用搜索；
2. 搜索 provider 返回候选；
3. 读取多个来源，每个来源还可能经历多次重定向或公网 IP 尝试；
4. 模型基于工具结果继续推理；
5. 若引用覆盖或语言不符合契约，再调用一次模型做有限修订。

每个网络操作都可以分别消耗自己的 timeout。即使每次都在上限前成功，累计时间仍可远大于
任意一个 transport timeout。读取过程中持续有数据也可能不断满足 read timeout，而没有一个
统一计时器终止整个研究。

Wall-clock deadline 应以单调时钟记录整次操作的绝对截止点，并把剩余预算传播到模型、搜索和
读取步骤；到期后还要取消或停止在途工作，再映射成稳定的终止结果。单纯把每个 transport
timeout 调小，无法得到这一语义。

## 当前项目实际设置了什么

### Ollama 模型 transport

`OLLAMA_TIMEOUT_SECONDS` 必须是正有限值，默认 300 秒。组合根把它作为
`ChatOllama` client 的 `timeout`，同时设置 `trust_env=False`。这限制本机 Ollama HTTP
transport 的阶段等待，并避免模型 client 继承系统 HTTP proxy。

模型调用抛出的异常会被研究服务归类为 fail-closed 的 `agent_error`，但这只规定失败结果，
没有增加总运行 deadline。

### Agent graph super-step 与工具并发

[LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api#recursion-limit)
把 `recursion_limit` 定义为一次执行允许的最大 super-step 数；达到上限会抛出
`GraphRecursionError`。这是 `invoke` 的独立 config key，不是 `configurable` 中的业务参数。

主研究 Agent 的 `invoke` 显式传入 `recursion_limit=100`，不继承可能随依赖版本变化的默认值。
因此模型若持续在推理节点和工具节点之间循环，最终会抛出异常；`ResearchService` 通过现有的
Agent 异常边界把它转换成 fail-closed `agent_error`，不会把未完成循环当作来源充分的报告。

[LangChain ToolNode reference](https://reference.langchain.com/python/langgraph.prebuilt/tool_node/ToolNode)
说明 ToolNode 管理并行工具执行；[RunnableConfig `max_concurrency`](https://reference.langchain.com/python/langchain-core/runnables/config/RunnableConfig/max_concurrency)
定义最大并行调用数，缺省时使用 `ThreadPoolExecutor` 默认值。一个 AI message 可以携带多个
tool call，它们仍只占工具节点所在的一个 super-step，所以 recursion limit 不会限制该 step
内部的 fan-out 宽度。

本项目的搜索、读取工具共享同一个请求内 `ResearchTools`：它维护候选 URL→source、S# 分配、
已读证据和 warnings。主图因此同时传入 `max_concurrency=1`，让 ToolNode 保留并执行模型请求的
全部 tool call，但一次只运行一个。这样 source registry 只有一个工具 mutator，ID 和结果顺序
不依赖本机 executor 宽度，也避免一条模型消息同时启动许多公网搜索或读取。

这里的 100 与单任务并发都是本项目为单题、状态型工具选择的策略，不是 LangGraph 标准推荐
值、生产容量测量或服务 SLA。Super-step 不等于工具调用，`max_concurrency=1` 也不限制整次图
累计多少次调用；DDGS 和 HTTP client 自己启动的内部工作不由该值计数。它们不能在节点内部
取消一个慢 Ollama/HTTP 调用，不能约束同步 DNS 或持续有进展的响应体，也不包含主图之后至多
一次的格式/语言修订模型调用。因此它们补充 transport timeout，但不能替代 wall-clock deadline。

### 页面读取与 DNS

`SafeHttpPageReader` 有独立的 10 秒 HTTPX timeout、默认 30 秒的连接尝试预算，以及响应大小、
正文字符数和最多三次重定向等边界。Fake-IP 公共 DNS 查询使用另一个 5 秒 timeout。这些限制
属于不同外部调用，`OLLAMA_TIMEOUT_SECONDS` 不会覆盖它们。

DoH client 与页面 reader 都显式设置 `trust_env=False`。系统 DNS 返回 Fake-IP 时，公网地址
再验证和随后固定 IP 的页面连接因此走同一条直连/TUN 网络边界，不会让 DoH 单独继承 shell
里的 HTTP(S) proxy。该设置不提供绕过网络策略的 fallback：若环境只允许显式 proxy、禁止
直连公网，公共 DNS 再验证会失败，reader 仍按安全契约 fail closed。

A 与 AAAA 各自最多尝试两次，每次仍使用独立的 5 秒 HTTPX timeout。一种地址族在两次尝试后
仍不可用时，只要另一种地址族已经返回至少一个地址，resolver 就用成功集合继续公网属性验证；
两种地址族都没有可用答案才把解析判为失败。这个策略处理单次握手超时和单地址族故障，但不
缓存 DNS、不跳过公网 IP 检查，也不是一个统一的 20 秒硬 deadline；最坏情况下两族各两次都
可能分别消耗 timeout。

30 秒是本项目的 reader 构造参数默认值，不是 HTTPX 标准值或生产延迟结论。一次 `read()`
只建立一个单调时钟 deadline，所有已验证公网地址和后续重定向都共享它。发起每个新 HTTPX
请求前，reader 计算：

```text
attempt timeout = min(10 秒 transport timeout, 连接尝试剩余预算)
```

剩余预算不大于零时不再发起请求，而是 fail closed。这样即使解析结果含很多地址，也不会让
每个地址都重新获得完整的 10 秒窗口；重定向也不会重置 30 秒预算。地址集合本身不会被截断。

如果结果同时含 IPv4 和 IPv6，校验器保留第一条地址代表的地址族偏好，也保留每个地址族内部
的相对顺序，然后一对一交错两族；某一族用尽后再附加另一族的剩余地址。reader 仍按这个列表
逐个同步尝试，没有并发或交错启动时间。这样一个受损地址族不会在有限预算内占满所有早期
尝试位置。

这里仅采用 [RFC 8305 第 4 节](https://www.rfc-editor.org/rfc/rfc8305.html#section-4) 的地址族
交错原则。[Python 3.12 `getaddrinfo` 文档](https://docs.python.org/3.12/library/socket.html#socket.getaddrinfo)
说明返回行为依赖系统，许多系统会提供已排序结果；本项目不重新实现 RFC 6724 排序，而是以
输入的首地址族和同族顺序为准。RFC 8305 还包括异步 DNS、错峰并发连接、成功后取消其他连接
等机制，当前同步 reader 都没有实现，因此不能声称符合完整 Happy Eyeballs。

这个机制仍不是整页硬 deadline。同步 DNS 解析不能被单调时钟检查从中途取消；如果它返回时
预算已耗尽，reader 只能在下一个 HTTP 请求前停止。连接成功后的响应体只受 HTTPX 的逐阶段
无进展 timeout 和大小上限约束，持续到达的小块数据不会因 30 秒绝对时刻自动取消。因此该
预算准确约束的是“是否继续发起地址/重定向连接尝试”，而不是 `read()` 的所有 wall-clock
工作。

### 尚未实现的边界

当前 `ResearchService.research` 外层没有整次运行的 wall-clock deadline。因此 README 和产品
契约只能声称“部分传输停顿、主图步骤数和任务并发宽度有界，并能 fail closed”，不能声称
“用户一定会在 300 秒内拿到结果”。

## 四类机制解决不同问题

- Transport timeout 回答：“某个 socket/连接池阶段多久没有进展就失败？”
- Recursion limit 回答：“这次图执行最多允许多少个 super-step？”
- Concurrency limit 回答：“同一时刻最多允许多少个图任务运行？”
- Wall-clock deadline 回答：“无论内部做了多少步，这个用户请求最晚何时必须结束？”

这些边界可以同时存在：transport timeout 应短到能从局部故障中恢复，recursion limit 防止
图拓扑无限循环，concurrency limit 控制单步 fan-out，deadline 则约束整次请求的延迟和资源
消耗。Deadline 到期时，内部 timeout 还应被压缩到“剩余预算”，否则外层虽已放弃，底层网络
调用仍可能继续占用资源。

## 当前实现与测试入口

- [`config.py`](../../src/agent_learn/config.py)：`OLLAMA_TIMEOUT_SECONDS` 默认值与配置校验。
- [`bootstrap.py`](../../src/agent_learn/bootstrap.py)：把 timeout 传给 `ChatOllama` client。
- [`adapters.py`](../../src/agent_learn/adapters.py)：主 Agent graph step/concurrency limit，以及
  页面读取器的独立 timeout、重定向和大小边界。
- [`security.py`](../../src/agent_learn/security.py)：Fake-IP 公共 DNS 查询的独立 timeout。
- [`test_security.py`](../../tests/unit/test_security.py)：Fake-IP 再解析和 DoH 不继承 proxy 的契约。
- [`test_adapters.py`](../../tests/unit/test_adapters.py)：共享预算、地址回退和重定向的确定性验证。
- [`test_config.py`](../../tests/unit/test_config.py)：拒绝零、负数、无穷和非数字配置。
- [`test_bootstrap.py`](../../tests/unit/test_bootstrap.py)：验证模型 transport 收到配置值且不继承 proxy。
