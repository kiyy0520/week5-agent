import argparse
import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client


REQUIRED_GOV_KEYS = {"version", "permissions", "side_effect", "timeout_ms", "retry_max", "retry_backoff_ms"}


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
    return True, ""


async def run_with_session(session: ClientSession):
    """与传输无关的会话逻辑：stdio 和 HTTP 共用这一段。"""
    await session.initialize()

    tools_result = await session.list_tools()
    print(f"发现工具数量: {len(tools_result.tools)}")

    projected = []
    rejected = []
    for t in tools_result.tools:
        ok, reason = check_compliance(t)
        if ok:
            projected.append(t.name)
            print(f"[投影] {t.name}")
        else:
            rejected.append((t.name, reason))
            print(f"[拒绝投影] {t.name} —— {reason}")

    print(f"合规并投影 {len(projected)} 个，拒绝 {len(rejected)} 个")

    if "get_order_status" not in projected:
        print("get_order_status 未通过合规检查，跳过调用")
        return

    result = await session.call_tool(
        "get_order_status",
        {"order_id": "ORD-20240101-001"},
    )

    if result.isError:
        print("调用失败:", result.content)
        return

    payload = json.loads(result.content[0].text)
    print("调用结果:", payload)
    print("trace_id:", payload["trace_id"])


async def main_stdio():
    server_params = StdioServerParameters(
        command="python",
        args=["mcp_server/server.py"],
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await run_with_session(session)


async def main_http(url: str):
    # 1.x 的 streamablehttp_client 返回 (read, write, get_session_id)，
    # 不同小版本可能返回二元组，这里用索引兼容。
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