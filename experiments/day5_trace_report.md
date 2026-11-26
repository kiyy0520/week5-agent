# Day 5 执行轨迹分层归因 + Badcase 标注报告

## 1. 任务概述

本报告完成 Day 5 任务：结构化执行日志、≥5 条 badcase 四层标注、四层错误率、CSV 交付物、面试问答草稿、失效条件记录。本次报告基于 9 条 badcase 进行量化分析。

## 2. 执行日志字段

| 字段 | 说明 |
|---|---|
| trace_id | 单次执行唯一编号，用于回放 |
| task_id | 任务身份，同一任务重跑可有多个 trace_id |
| step | 步骤序号 |
| tool | 本步调用的工具 |
| params | 本步参数 |
| result | 工具返回或错误摘要 |
| elapsed_ms | 耗时（毫秒） |
| error_type | None/timeout/429/5xx/empty/schema_error/unknown_error |
| is_retry | 是否重试 |
| is_approval | 是否审批 |

## 3. Badcase 清单

| trace_id | task_id | badcase_type | layer | root_cause | evidence |
|---|---|---|---|---|---|
| trace_xxx | task_001 | 工具选择错误 | 工具选择 | 意图识别偏差，该选 weather_query 却选 news_search | step1 tool=news_search |
| trace_xxx | task_002 | 参数错误 | 参数生成 | 枚举越界，传入 '上海浦东新区' | step1 params.city=上海浦东新区 |
| trace_xxx | task_003 | 工具返回异常 | 工具返回 | 下游天气服务超时，重试 2 次仍失败 | step1 error_type=timeout, is_retry=true |
| trace_xxx | task_004 | 忽略返回 | 忽略返回 | 模型未采用晴天结果，回答可能下雨 | step1 result=晴天; final_answer=可能下雨 |
| trace_xxx | task_005 | 参数错误 | 参数生成 | 缺必填参数 b | step1 params 缺 b, error_type=schema_error |
| trace_xxx | task_006 | 工具选择错误 | 工具选择 | 该选未选，未调工具直接回答 | trace 中无 tool 调用 step |
| trace_xxx | task_007 | 参数错误 | 参数生成 | 参数越界（divide）导致下游报错，且模型忽略报错 | step1 error_type=schema_error; final_answer=0 |
| trace_xxx | task_008 | 工具返回异常 | 工具返回 | 下游 429 限流，重试失败，且模型忽略报错 | step1 error_type=429, is_retry=true; final_answer=成功 |
| trace_xxx | task_009 | 安全越权 | 工具选择 | 高危操作绕过了审批流程直接执行 | step1 need_approval=False, result=deleted |

## 4. 四层错误率

统一分母 N = 9（总 badcase 条数）。逐层命中独立统计，一条 badcase 可多层命中，因此四层错误率相加可能超过 100%。

| 层 | 命中数 | 分母 | 错误率 |
|---|---|---|---|
| 工具选择 | 3 | 9 | 33.3% |
| 参数生成 | 3 | 9 | 33.3% |
| 工具返回 | 3 | 9 | 33.3% |
| 忽略返回 | 3 | 9 | 33.3% |

## 5. 失效模式分析

| 失效类型 | 表现 | 根因 | 治理动作 |
|---|---|---|---|
| 工具选择错误 | 选错工具、该选未选、绕过高危审批 | Schema 投影/权限/模型意图偏差 | Registry 过滤 + 工具选择评测 + 强制人工确认 |
| 参数错误 | 缺参、类型错、枚举越界 | 模型生成不稳定 | JSON Schema 校验 + 结构化回传 |
| 工具返回异常 | 超时、429、5xx、空返回 | 下游不稳定 | Timeout/Retry/Fallback/熔断 |
| 忽略返回 | 模型不采用工具结果 | 上下文/提示/结果过大 | 结果校验 + 后置验证 + 截断摘要 |

## 6. 可量化验证结果

- ≥5 条 badcase 完成四层标注：9 条。
- 四层错误率全部有数字：工具选择 33.3%；参数生成 33.3%；工具返回 33.3%；忽略返回 33.3%。
- 每条 badcase 能定位到具体层，并有日志证据：见第 3 节表格。
- 执行日志字段完整，可按 trace_id 回放：`validate_trace_replay` 已校验通过。

## 7. 失效条件

当前四层归因假设是单 Agent 调用工具。多 Agent 协作时，错误可能发生在 Agent 之间的交接：上一步 Agent 的输出格式、语义、权限不符合下游 Agent 预期。此时需扩展第五层“Agent 间交接”层，记录交接协议、字段映射、权限边界，否则会把交接错误误判为工具选择或参数生成错误。