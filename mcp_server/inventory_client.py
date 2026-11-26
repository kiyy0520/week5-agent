import argparse
import asyncio
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

REQUIRED_GOV_KEYS = {
    "version", "permissions", "side_effect",
    "timeout_ms", "retry_max", "retry_backoff_ms",
}


def parse_governance(description: str) -> dict | None:
    if not description or "[GOV]" not in description:
        return None
    first_line = description.splitlines()[0]
    body = first_line.replace("[GOV]", "").strip()
    gov = {}
    for part in body.split("|"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        gov[k.strip()] = v.strip()
    return gov


def check_compliance(tool) -> tuple[bool, str]:
    gov = parse_governance(tool.description or "")
    if gov is None:
        return False, "缺少 [GOV] 治理元数据块"

    missing = REQUIRED_GOV_KEYS - set(gov.keys())
    if missing:
        return False, f"治理元数据缺字段: {sorted(missing)}"

    if tool.annotations is None or getattr(tool.annotations, "readOnlyHint", None) is None:
        return False, "缺少 annotations.readOnlyHint 提示位"

    if gov.get("side_effect") == "write":
        props = (tool.inputSchema or {}).get("properties", {})
        if "idempotency_key" not in props:
            return False, "写工具的 inputSchema 缺少 idempotency_key"

    if gov.get("side_effect") == "read_only" and tool.annotations.readOnlyHint is not True:
        return False, "side_effect=read_only 与 readOnlyHint 矛盾"

    return True, ""


async def call_and_print(session, name: str, args: dict, label: str):
    """统一处理调用结果：区分 isError 与成功，打印 trace_id。"""
    print(f"\n--- {label} ---")
    result = await session.call_tool(name, args)
    if result.isError:
        # 工具内抛异常时，content[0].text 是错误文本，不是 JSON
        err_text = result.content[0].text if result.content else "(无内容)"
        print(f"[isError=True] {err_text}")
        return
    payload = json.loads(result.content[0].text)
    print(f"[成功] {payload}")
    print(f"trace_id: {payload.get('trace_id')}")


async def run_with_session(session: ClientSession):
    await session.initialize()

    tools_result = await session.list_tools()
    print(f"发现工具数量: {len(tools_result.tools)}")

    projected, rejected = [], []
    for t in tools_result.tools:
        ok, reason = check_compliance(t)
        if ok:
            projected.append(t.name)
            print(f"[投影] {t.name}")
        else:
            rejected.append((t.name, reason))
            print(f"[拒绝投影] {t.name} —— {reason}")
    print(f"合规并投影 {len(projected)} 个，拒绝 {len(rejected)} 个")

    # 只读调用
    if "check_stock" in projected:
        await call_and_print(session, "check_stock",
                             {"sku": "SKU-1001", "warehouse": "ALL"}, "只读：查全部仓库存")

    # 写调用：只对已投影的 transfer_stock 操作
    if "transfer_stock" not in projected:
        print("transfer_stock 未通过合规检查，跳过写调用")
        return

    # ① 正常调拨
    await call_and_print(session, "transfer_stock", {
        "sku": "SKU-1001", "from_warehouse": "WH-SH", "to_warehouse": "WH-BJ",
        "quantity": 10, "idempotency_key": "transfer-key-001",
    }, "写：正常调拨 10 件 WH-SH -> WH-BJ")

    # ② 幂等重放：同一个 key，应返回 replayed=True，库存不再变
    await call_and_print(session, "transfer_stock", {
        "sku": "SKU-1001", "from_warehouse": "WH-SH", "to_warehouse": "WH-BJ",
        "quantity": 10, "idempotency_key": "transfer-key-001",
    }, "写：重复同一 idempotency_key（应为 replayed=True）")

    # ③ 源仓 = 目标仓：应 isError
    await call_and_print(session, "transfer_stock", {
        "sku": "SKU-1001", "from_warehouse": "WH-SH", "to_warehouse": "WH-SH",
        "quantity": 5, "idempotency_key": "transfer-key-002",
    }, "写：源仓=目标仓（应 isError=True）")

    # ④ 库存不足：SKU-2002 WH-SH 只有 5，调 100，应 isError
    await call_and_print(session, "transfer_stock", {
        "sku": "SKU-2002", "from_warehouse": "WH-SH", "to_warehouse": "WH-BJ",
        "quantity": 100, "idempotency_key": "transfer-key-003",
    }, "写：库存不足（应 isError=True）")


async def main_stdio():
    params = StdioServerParameters(command="python", args=["mcp_server/inventory_server.py"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await run_with_session(session)


async def main_http(url: str):
    async with streamablehttp_client(url) as streams:
        read, write = streams[0], streams[1]
        async with ClientSession(read, write) as session:
            await run_with_session(session)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--url", default="http://127.0.0.1:8000/mcp")
    args = parser.parse_args()

    if args.transport == "stdio":
        asyncio.run(main_stdio())
    else:
        asyncio.run(main_http(args.url))