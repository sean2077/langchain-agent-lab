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

`SafeHttpPageReader` 有独立的 10 秒 HTTPX timeout、默认 30 秒的连接尝试预算，以及响应大小、
正文字符数和最多三次重定向等边界。Fake-IP 公共 DNS 查询使用另一个 5 秒 timeout。这些限制
属于不同外部调用，`OLLAMA_TIMEOUT_SECONDS` 不会覆盖它们。

30 秒是本项目的 reader 构造参数默认值，不是 HTTPX 标准值或生产延迟结论。一次 `read()`
只建立一个单调时钟 deadline，所有已验证公网地址和后续重定向都共享它。发起每个新 HTTPX
请求前，reader 计算：

```text
attempt timeout = min(10 秒 transport timeout, 连接尝试剩余预算)
```

剩余预算不大于零时不再发起请求，而是 fail closed。这样即使解析结果含很多地址，也不会让
每个地址都重新获得完整的 10 秒窗口；重定向也不会重置 30 秒预算。地址集合本身不会被截断或
重排，预算允许时仍按验证器给出的顺序回退。当前实现没有并发竞速地址，也不声称实现了
Happy Eyeballs。

这个机制仍不是整页硬 deadline。同步 DNS 解析不能被单调时钟检查从中途取消；如果它返回时
预算已耗尽，reader 只能在下一个 HTTP 请求前停止。连接成功后的响应体只受 HTTPX 的逐阶段
无进展 timeout 和大小上限约束，持续到达的小块数据不会因 30 秒绝对时刻自动取消。因此该
预算准确约束的是“是否继续发起地址/重定向连接尝试”，而不是 `read()` 的所有 wall-clock
工作。

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
- [`test_adapters.py`](../../tests/unit/test_adapters.py)：共享预算、地址回退和重定向的确定性验证。
- [`test_config.py`](../../tests/unit/test_config.py)：拒绝零、负数、无穷和非数字配置。
- [`test_bootstrap.py`](../../tests/unit/test_bootstrap.py)：验证模型 transport 收到配置值且不继承 proxy。
