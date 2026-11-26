# Day 1 实验总结：Tool Registry 与 Schema 治理

## 1. 实验背景与目标
在构建多步 Agent 的过程中，最大的风险之一是模型幻觉导致的“参数乱传”与“越权调用”。本次实验（Day 1）的核心目标是建立一个轻量、安全的工程底座，验证以下机制的有效性：
- **Tool Registry** 的注册与版本冲突检测。
- **运行时工具投影** 的物理级权限隔离。
- **JSON Schema** 在模型输出后、执行前的强制安检。
- **结构化 ToolError** 对异常链路的标准化治理。
- 隔离旧项目（week2-4）重型依赖，验证 RAG 薄契约的可行性。

## 2. 实验环境与配置
- **架构**：独立应用层 `week5-agent/`（完全隔离于 week2-4）。
- **Python 环境**：3.10+ (使用 `.venv` 虚拟环境)。
- **核心依赖（requirements.txt）**：`jsonschema`, `pytest`, `fastapi`, `uvicorn`, `pydantic`。
- **依赖硬边界**：严格排除 `chromadb`、`rank_bm25`、`ragas`。

## 3. 核心治理机制实现与对比

### 3.1 Tool Registry：双层字典与冲突检测
- **实现方式**：使用 `Dict[str, Dict[str, ToolMeta]]`（第一层为工具名，第二层为版本号）。
- **对比**：如果使用普通数组（List），新增同名工具会直接覆盖旧工具，导致线上系统崩溃且难以排查。
- **结果**：成功拦截同名同版本重复注册，并抛出 `ToolConflictError`（`retryable=False`）。

### 3.2 运行时投影 vs Prompt 道德约束
- **实现方式**：`get_allowed_tools(user_permissions)` 根据当前身份，动态生成允许调用的工具 Schema 列表。
- **对比**：在 Prompt 中写“禁止调用 delete_user”防不住大模型的幻觉；而运行时投影直接不给 Guest 身份下发 `delete_user` 的说明书。
- **结果**：Guest 只能看到 2 个工具（Weather、Search），物理级阻断了越权风险。

### 3.3 Schema 校验拦截矩阵
针对模型常见的输出错误，我们设计了四维拦截机制，且在工具执行前完成：
- **参数缺失**：必填项未传（如缺失 `query`） -> 拦截成功。
- **类型错误**：如年龄传了字符串 `"twenty"` -> 拦截成功。
- **枚举越界**：如天气单位传了 `"K"`（只允许 C/F） -> 拦截成功。
- **范围越界**：如 BMI 测试中身高传了 `-1`（最小 0.1） -> 拦截成功。

### 3.4 RAG 检索链路的降级决策
- **实现方式**：在 `adapters/rag_tool.py` 中仅定义 `search_knowledge(query: str, top_k: int = 5)` 接口契约，内部抛出 `NotImplementedError`。
- **对比**：不将完整的 Chroma+BM25+RAGAS 搬入。如果直接搬入，会导致环境臃肿，且检索调优会喧宾夺主，冲淡本周的 Agent 治理主线。
- **失效条件**：若下周需专门做 RAG 检索质量评估，应拆分至独立项目。

## 4. 自动化验收结果 (pytest)
在终端运行 `python -m pytest tests/test_registry.py -v`，成功达成 **6 个 PASSED**：
1. `test_tool_conflict_detection`：冲突检测触发 `ToolConflictError`，含 `trace_id`。
2. `test_runtime_tool_projection`：Guest 3 个/Admin 4 个，Guest 成功过滤掉 `delete_user`。
3. `test_schema_enum_validation`：枚举越界拦截，`retryable=False`。
4. `test_schema_missing_param_validation`：必填缺失拦截，报错含 `required property`。
5. `test_bmi_tool`：BMI 工具注册与范围拦截。
6. `test_user_info_tool_type_validation`：类型校验及正常调用（`25`）与异常调用（`"twenty"`）的双重验证。

## 5. 踩坑与解决记录（后续开发警戒）
- **`ModuleNotFoundError: No module named 'tools'`**：pytest 默认路径不包含根目录。必须在根目录新增 `pytest.ini`，配置 `pythonpath = .`。
- **断言因工具数量变更而失败**：新增 BMI 工具后，修改了 Fixture，必须同步更新投影测试中的断言预期值（Guest 从 2 改为 3，Admin 从 3 改为 4）。说明测试是“活”的，需持续维护。
- **`NotImplementedError` 的重要性**：如果在 RAG 契约里写 `pass`，函数会返回 `None`，后续 Agent 按列表解析会报 `TypeError: 'NoneType' object is not iterable`，且极难排查。抛错能明确阻断。

## 6. 结论与明日衔接
Day 1 成功建立了一个“**注册防冲突、投影防越权、Schema防幻觉、Error带追踪**”的坚固工具底座。
**下一步（Day 2）**：在此底座之上，我们将引入 LLM 与 ReAct 循环（Think-Act-Observe），并开始对比“裸 LLM”与“受约束 Policy”下的 Agent 表现差异。