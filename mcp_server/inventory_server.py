import sys
import uuid

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

mcp = FastMCP("day3-inventory-server")

# 模拟库存：{(sku, warehouse): available}
_STOCK = {
    ("SKU-1001", "WH-SH"): 120,
    ("SKU-1001", "WH-BJ"): 30,
    ("SKU-2002", "WH-SH"): 5,
    ("SKU-2002", "WH-BJ"): 50,
}

# 幂等记录：idempotency_key -> 上次结果（重放时直接返回，不再执行）
_TRANSFER_LOG: dict[str, dict] = {}


@mcp.tool(
    name="check_stock",
    description=(
        "[GOV] version=1.0.0 | permissions=inventory:read | side_effect=read_only | "
        "timeout_ms=2000 | retry_max=2 | retry_backoff_ms=150\n"
        "查询指定 SKU 在各仓库的可用库存。只读操作，不改变任何数据。"
    ),
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True),
)
def check_stock(sku: str, warehouse: str = "ALL") -> dict:
    """按 SKU 查库存；warehouse 可选，默认查全部仓库。"""
    trace_id = f"trace-{uuid.uuid4().hex[:12]}"
    if warehouse == "ALL":
        snapshot = {wh: qty for (s, wh), qty in _STOCK.items() if s == sku}
    else:
        snapshot = {warehouse: _STOCK.get((sku, warehouse), 0)}
    return {"sku": sku, "warehouse": warehouse, "stock": snapshot, "trace_id": trace_id}


@mcp.tool(
    name="transfer_stock",
    description=(
        "[GOV] version=1.0.0 | permissions=inventory:transfer | side_effect=write | "
        "timeout_ms=5000 | retry_max=0 | retry_backoff_ms=0\n"
        "跨仓调拨库存：从 from_warehouse 扣减，向 to_warehouse 增加。写操作，影响两个仓库。"
        "必须携带 idempotency_key；同一键重放不会重复扣减。"
        "校验：源仓 ≠ 目标仓、数量 > 0、源仓可用库存 ≥ 调拨数量。"
    ),
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True),
)
def transfer_stock(
    sku: str,
    from_warehouse: str,
    to_warehouse: str,
    quantity: int,
    idempotency_key: str,
) -> dict:
    """跨仓调拨；同一 idempotency_key 重放返回上次结果，不重复执行。"""
    # ① 幂等重放：命中就直接返回上次结果，不再动库存
    if idempotency_key in _TRANSFER_LOG:
        replay = dict(_TRANSFER_LOG[idempotency_key])
        replay["replayed"] = True
        return replay

    # ② 业务校验：运行时值是否合法，必须在工具内做
    if from_warehouse == to_warehouse:
        raise ValueError(f"源仓与目标仓不能相同: {from_warehouse}")
    if quantity <= 0:
        raise ValueError(f"调拨数量必须为正: {quantity}")

    src_key = (sku, from_warehouse)
    dst_key = (sku, to_warehouse)
    available = _STOCK.get(src_key, 0)
    if available < quantity:
        raise ValueError(
            f"源仓 {from_warehouse} 库存不足: 需要 {quantity}, 可用 {available}"
        )

    # ③ 执行：两仓同时变更
    _STOCK[src_key] = available - quantity
    _STOCK[dst_key] = _STOCK.get(dst_key, 0) + quantity

    trace_id = f"trace-{uuid.uuid4().hex[:12]}"
    result = {
        "sku": sku,
        "from_warehouse": from_warehouse,
        "to_warehouse": to_warehouse,
        "quantity": quantity,
        "idempotency_key": idempotency_key,
        "from_after": _STOCK[src_key],
        "to_after": _STOCK[dst_key],
        "replayed": False,
        "trace_id": trace_id,
    }
    _TRANSFER_LOG[idempotency_key] = result
    return result


@mcp.tool(
    name="search_products",
    description=(
        "[GOV] version=1.2.0 | permissions=inventory:read | side_effect=read_only | "
        "timeout_ms=3000 | retry_max=1 | retry_backoff_ms=200\n"
        "按关键词搜索商品，可限定分类与返回条数。只读操作。"
    ),
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True),
)
def search_products(keyword: str, category: str | None = None, limit: int = 10) -> dict:
    """搜索商品；category 可选，limit 默认 10。"""
    trace_id = f"trace-{uuid.uuid4().hex[:12]}"
    return {"keyword": keyword, "category": category, "limit": limit, "hits": [], "trace_id": trace_id}


@mcp.tool(
    name="force_delete_sku",
    description="强制删除 SKU。危险操作。",   # 故意没有 [GOV] 和 annotations
)
def force_delete_sku(sku: str) -> dict:
    return {"deleted": sku}


if __name__ == "__main__":
    transport = "streamable-http" if "--http" in sys.argv else "stdio"
    mcp.run(transport=transport)