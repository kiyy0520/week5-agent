# Day 3：MCP Server + 工具发现 + 治理元数据

## 1. 环境
- Python 版本：（填 `python --version` 输出）
- mcp SDK 版本：1.x（`pip show mcp` 的 Version）

## 2. Server 暴露的工具（4 个，含 1 个故意不合规）
| 工具 | 副作用 | 权限 | 超时 | 重试 | 治理元数据 |
|---|---|---|---|---|---|
| get_order_status | read_only | orders:read | 3000ms | 2 | 合规 |
| create_ticket | write | tickets:write | 5000ms | 0（幂等键去重） | 合规 |
| search_docs | read_only | docs:read | 4000ms | 1 | 合规 |
| delete_order | —（未声明） | —（未声明） | — | — | 故意缺失，用于验证守门 |

## 3. Client 发现与投影输出（stdio）
发现工具数量: 4
[投影] get_order_status
[投影] create_ticket
[投影] search_docs
[拒绝投影] delete_order —— 缺少 [GOV] 治理元数据块
合规并投影 3 个，拒绝 1 个
调用结果: {'order_id': 'ORD-20240101-001', 'status': 'paid', 'trace_id': 'trace-f3f7f0344e72'}
trace_id: trace-f3f7f0344e72

## 4. Client 发现与投影输出（Streamable HTTP）
发现工具数量: 4
[投影] get_order_status
[投影] create_ticket
[投影] search_docs
[拒绝投影] delete_order —— 缺少 [GOV] 治理元数据块
合规并投影 3 个，拒绝 1 个
调用结果: {'order_id': 'ORD-20240101-001', 'status': 'paid', 'trace_id': 'trace-554ea2c315a3'}
trace_id: trace-554ea2c315a3
结论：两种传输下会话逻辑完全一致，仅“流的来源”不同。

## 5. 合规守门规则
- 必须有 `[GOV]` 前缀块，含 6 个键：version / permissions / side_effect / timeout_ms / retry_max / retry_backoff_ms
- 必须有 `annotations.readOnlyHint` 提示位
- 任一缺失 → 拒绝投影，并给出原因
- 结果：delete_order 被拒，其余 3 个投影

## 6. 传输选择决策
- 本地开发：选 stdio，因为 Client 自动拉起 Server 子进程，零网络配置，调试最快。
  失效条件：需要多进程共享同一个 Server 时失效（stdio 一 Client 一子进程，无法共享）。
- 单机演示（多进程共享同一 Server）：选 Streamable HTTP + 绑定 127.0.0.1，
  因为需要多个独立进程连同一个 Server 实例。
  失效条件：不加 token 校验就暴露在网络上；绑定 0.0.0.0 且无认证时失效。
- 远程多租户：选 Streamable HTTP + OAuth 2.1 资源服务器（token 校验 + audience binding），
  因为多用户按 URL 接入，必须按身份隔离。
  失效条件：无认证、无租户隔离、Registry 不做身份过滤时失效。
- 企业接入：选 Streamable HTTP + OAuth + Registry 准入，
  因为涉及权限、审计、多团队工具治理。
  失效条件：工具级权限不落到 Registry、审计缺失、依赖模型“自己读警告”时失效。

## 7. 失效条件汇总
- stdio：远程多租户失效；多进程共享同一 Server 失效
- Streamable HTTP：不加认证即上生产 = 失效；依赖连接级状态 = 在新协议下失效
- Registry 过滤：单身份单租户演示可简化；企业不能省

## 8. 结论：MCP 的边界
MCP 解决接入标准化（发现、Schema、调用协议），不解决业务正确性和企业安全。
具体落点：
- 幂等键、超时、重试策略是应用层责任，协议只提供 annotations 提示位
- 权限和租户隔离靠 Server 端鉴权 + Registry 过滤，不靠工具描述
- “标记但投影”不能替代拦截，写工具场景不可接受