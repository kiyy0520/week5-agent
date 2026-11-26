from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
import uuid

mcp = FastMCP("day3-governance-server")


@mcp.tool(
    name="get_order_status",
    description=(
        "[GOV] version=1.0.0 | permissions=orders:read | side_effect=read_only | "
        "timeout_ms=3000 | retry_max=2 | retry_backoff_ms=200\n"
        "查询指定订单的当前状态。只读操作，不改变任何数据。"
    ),
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True),
)
def get_order_status(order_id: str) -> dict:
    """根据订单号返回订单状态。"""
    trace_id = f"trace-{uuid.uuid4().hex[:12]}"
    return {"order_id": order_id, "status": "paid", "trace_id": trace_id}


@mcp.tool(
    name="create_ticket",
    description=(
        "[GOV] version=1.0.0 | permissions=tickets:write | side_effect=write | "
        "timeout_ms=5000 | retry_max=0 | retry_backoff_ms=0\n"
        "创建一个客服工单。写操作，幂等键为 idempotency_key，重复提交同一键不会重复建单。"
    ),
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True),
)
def create_ticket(title: str, idempotency_key: str) -> dict:
    """创建工单，必须带幂等键。"""
    trace_id = f"trace-{uuid.uuid4().hex[:12]}"
    return {"ticket_id": "T-1001", "title": title, "idempotency_key": idempotency_key, "trace_id": trace_id}


@mcp.tool(
    name="search_docs",
    description=(
        "[GOV] version=1.1.0 | permissions=docs:read | side_effect=read_only | "
        "timeout_ms=4000 | retry_max=1 | retry_backoff_ms=300\n"
        "按关键词搜索文档，可限定标签列表与返回条数。只读操作。"
    ),
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True),
)
def search_docs(keyword: str, tags: list[str] | None = None, limit: int = 5) -> dict:
    """搜索文档；tags 可选，limit 默认 5。"""
    trace_id = f"trace-{uuid.uuid4().hex[:12]}"
    return {"keyword": keyword, "tags": tags or [], "limit": limit, "hits": [], "trace_id": trace_id}

@mcp.tool(
    name="delete_order",
    description="删除订单。危险操作。",   # 故意没有 [GOV] 前缀
)
def delete_order(order_id: str) -> dict:
    return {"deleted": order_id}

if __name__ == "__main__":
    import sys
    transport = "streamable-http" if "--http" in sys.argv else "stdio"
    mcp.run(transport=transport)