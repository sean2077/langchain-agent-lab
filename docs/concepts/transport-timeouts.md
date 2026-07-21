# 传输超时与总时限

## 问题

HTTPX 的 connect/read/write/pool transport timeout，与整个 Agent run 的 wall-clock
deadline 有什么区别？

## 简短答案

Transport timeout 限制一次 HTTP 操作在某个 I/O 阶段最多等待多久；wall-clock deadline
限制整次 `research(...)` 从开始到结束最多经过多久。前者能防止一个连接阶段永久停住，但
不会自动约束多次模型调用、工具调用、重定向和修订调用累计起来的总时长。

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

### 页面读取与 DNS

`SafeHttpPageReader` 有独立的 10 秒 HTTPX timeout，并有响应大小、正文字符数和最多三次
重定向等边界。Fake-IP 公共 DNS 查询使用另一个 5 秒 timeout。这些限制属于不同外部调用，
`OLLAMA_TIMEOUT_SECONDS` 不会覆盖它们。

### 尚未实现的边界

当前 `ResearchService.research` 外层没有整次运行的 wall-clock deadline。因此 README 和产品
契约只能声称“传输停顿有界并 fail closed”，不能声称“用户一定会在 300 秒内拿到结果”。

## 两类机制解决不同问题

- Transport timeout 回答：“某个 socket/连接池阶段多久没有进展就失败？”
- Wall-clock deadline 回答：“无论内部做了多少步，这个用户请求最晚何时必须结束？”

生产系统通常需要两者：transport timeout 应短到能从局部故障中恢复，deadline 则约束整次
请求的延迟和资源消耗。Deadline 到期时，内部 timeout 还应被压缩到“剩余预算”，否则外层虽已
放弃，底层网络调用仍可能继续占用资源。

## 当前实现与测试入口

- [`config.py`](../../src/agent_learn/config.py)：`OLLAMA_TIMEOUT_SECONDS` 默认值与配置校验。
- [`bootstrap.py`](../../src/agent_learn/bootstrap.py)：把 timeout 传给 `ChatOllama` client。
- [`adapters.py`](../../src/agent_learn/adapters.py)：页面读取器的独立 timeout、重定向和大小边界。
- [`security.py`](../../src/agent_learn/security.py)：Fake-IP 公共 DNS 查询的独立 timeout。
- [`test_config.py`](../../tests/unit/test_config.py)：拒绝零、负数、无穷和非数字配置。
- [`test_bootstrap.py`](../../tests/unit/test_bootstrap.py)：验证模型 transport 收到配置值且不继承 proxy。
