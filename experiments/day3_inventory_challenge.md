# Day 3 独立挑战：库存管理场景 MCP Server + Client

## 1. 环境
- Python 版本：【填 python --version 输出】
- mcp SDK 版本：【填 pip show mcp 的 Version】
- 运行目录：F:\Projects\week5-agent

## 2. 工具设计（4 个，含 1 个故意不合规）

| 工具 | 副作用 | 权限 | 超时 | 重试 | 防重设计 | 治理状态 |
|---|---|---|---|---|---|---|
| check_stock | read_only | inventory:read | 2000ms | 2 | 只读，无需 | 合规 |
| reserve_stock | write | inventory:write | 5000ms | 0 | idempotency_key + 不自动重试 | 合规 |
| search_products | read_only | inventory:read | 3000ms | 1 | 只读，无需 | 合规 |
| force_delete_sku | 未声明 | 未声明 | 未声明 | 未声明 | 无 | 故意裸工具，验证守门 |

设计说明：
- reserve_stock 是写操作，retry_max=0 表示默认不自动重试；调用方如需重发，靠 idempotency_key 去重。
  两者缺一不可：只设 retry_max=0 没有幂等键，调用方自己重发仍会重复扣减；
  只有幂等键但 retry_max>0，自动重试路径不受控。
- force_delete_sku 故意不写 [GOV] 和 annotations，用来证明“发现得到 ≠ 能投影”。

## 3. 合规守门规则（三层）

1. **块存在**：description 第一行必须有 [GOV] 前缀块。
2. **字段齐全**：version / permissions / side_effect / timeout_ms / retry_max / retry_backoff_ms 六项齐全，
   且 annotations.readOnlyHint 不为 None。
3. **自洽性检查**：
   - side_effect=write → inputSchema.properties 必须含 idempotency_key；
   - side_effect=read_only → readOnlyHint 必须为 True。

判定结果：3 个合规并投影，force_delete_sku 被拒绝并给出具体原因。

## 4. stdio 模式真实输出

```text
(.venv) PS F:\Projects\week5-agent> python mcp_server/inventory_client.py
发现工具数量: 4
[投影] check_stock
[投影] reserve_stock
[投影] search_products
[拒绝投影] force_delete_sku —— 缺少 [GOV] 治理元数据块
合规并投影 3 个，拒绝 1 个
调用结果: {'sku': 'SKU-1001', 'warehouse': 'WH-SH', 'available': 120, 'reserved': 15, 'trace_id': 'trace-baffa4731e9c'}
trace_id: trace-baffa4731e9c
```

## 5. Streamable HTTP 模式真实输出

终端 A（Server）启动输出：
```text
【粘贴 python mcp_server/inventory_server.py --http 的前几行，能看到监听地址】
```

终端 B（Client）输出：
```text
(.venv) PS F:\Projects\week5-agent> python mcp_server/inventory_client.py --transport http
发现工具数量: 4
[投影] check_stock
[投影] reserve_stock
[投影] search_products
[拒绝投影] force_delete_sku —— 缺少 [GOV] 治理元数据块
合规并投影 3 个，拒绝 1 个
调用结果: {'sku': 'SKU-1001', 'warehouse': 'WH-SH', 'available': 120, 'reserved': 15, 'trace_id': 'trace-5c3bbd4273d4'}
trace_id: trace-5c3bbd4273d4
```

## 6. 双传输对比结论

- 两种模式输出结构一致：发现 4 → 投影 3 → 拒绝 1 → 调用 check_stock 成功 → 打印 trace_id。
- 差异只在“流的来源”：stdio 由 Client 拉起子进程；HTTP 由 Client 连独立 Server 的 URL。
- 会话逻辑（initialize / list_tools / check_compliance / call_tool）只写一份，位于 run_with_session，两条传输路径共用。治理规则改动只需改一处。

## 7. 三方使用者场景的传输与过滤决策

场景：仓库管理员（读写）、采购员（查库存 + 预占）、财务（只读核对）。

- **传输选择：Streamable HTTP + OAuth 2.1 资源服务器。**
  理由：三方在不同地点、不同设备，需要共享同一个 Server 实例；
  stdio 是一 Client 一子进程，三方各拉各的，库存状态不共享，直接失效。
- **认证**：token 携带角色声明（warehouse_admin / buyer / finance）。
- **Registry 按角色过滤工具可见性**：
  - 财务：只投影 check_stock、search_products；
  - 采购员：投影 check_stock、search_products、reserve_stock；
  - 仓库管理员：投影全部合规工具。
- **失效条件**：
  1. Streamable HTTP 不加 token 校验直接暴露公网 → 失效，任何人可调 reserve_stock；
  2. Registry 只做“有 [GOV] 就投影”、不按角色过滤 → 财务能看到 reserve_stock，越权风险；
  3. 用“给模型加警告”代替拒绝投影 → 模型是概率性的，警告不是拦截，写操作不可逆。

## 8. 结论：MCP 的边界

MCP 解决接入标准化（发现、Schema、调用协议），不解决业务正确性和企业安全。
本场景落点：
- 不解决业务正确性：reserve_stock 的幂等去重、retry_max=0、超时策略，都是应用层自己定的；
  协议只给 annotations 提示位，提示准不准没有保证。
- 不解决企业安全：force_delete_sku 缺治理元数据，MCP 照样暴露它；
  拦住它的是 Client 侧 check_compliance（Registry 过滤），不是 MCP。
  三方角色隔离、OAuth 认证，也都是应用层补的。

  ## 9. 变式：transfer_stock 跨仓调拨

### 9.1 工具定义
| 工具 | 副作用 | 权限 | 超时 | 重试 | 防重设计 |
|---|---|---|---|---|---|
| transfer_stock | write | inventory:transfer | 5000ms | 0 | idempotency_key；重放返回旧结果且标记 replayed=True |

### 9.2 业务校验（工具内，运行时值）
- 源仓 = 目标仓 → 抛 ValueError → isError=True
- quantity <= 0 → 抛 ValueError → isError=True
- 源仓可用 < quantity → 抛 ValueError，错误信息说明“哪个仓、缺多少”

### 9.3 守门层为什么不为“源仓≠目标仓”加检查
守门层只能看到声明（description / inputSchema / annotations），看不到运行时传入的具体值。
“源仓≠目标仓”是运行时参数之间的约束，必须放在工具内部。
守门层已有的“side_effect=write → Schema 必须含 idempotency_key”是声明层自洽检查，
transfer_stock 自动复用，无需新增。
结论：守门层管“声明是否自洽”，工具层管“运行时值是否合法”，两者不能互相替代。

### 9.4 幂等语义
同一 idempotency_key 重放时：直接返回上次结果，不再执行扣减，trace_id 沿用上次的，
并加 replayed=True 标记，语义上告知调用方“本次没有真正执行”。
校验顺序：幂等检查 → 业务校验 → 执行。
若校验放在幂等检查之前，重放时参数若被改成非法值会报错，违背“重放应无害返回”的语义。

### 9.5 transfer_stock 的角色可见性
| 角色 | 能否调用 transfer_stock | 理由 |
|---|---|---|
| 仓库管理员 / 调度员 | 能 | 调拨属于仓储调度职责 |
| 采购员 | 不能 | 调拨会改变两仓库存分布，影响订单履约，不属于采购职责 |
| 财务 | 不能 | 只读核对，无调度权 |

### 9.6 跨租户仓库的隔离放哪一层
不能靠工具描述。工具描述写“仅限同租户”没有拦截力，模型看得到、调得到。
隔离必须落在两处：
1. Server 侧：校验 token 中的租户身份；
2. 数据层：_STOCK 的读写必须按租户过滤，即使工具被调用也读不到别的租户的仓库。
失效条件：_STOCK 是全局字典、Server 只校验“有没有 token”不校验“token 属于哪个租户”，
则 A 租户管理员可把货调到 B 租户仓库，工具描述拦不住。