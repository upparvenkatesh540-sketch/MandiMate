"""Inventory MCP server: narrow, typed stock tools. Runs over stdio."""
from mcp.server.fastmcp import FastMCP
from common import db, require_write, audit

mcp = FastMCP("inventory")

@mcp.tool()
def check_stock(product: str, quantity: float) -> dict:
    """Check whether `quantity` of a product (canonical English name) is in stock."""
    r = db().table("products").select("*").ilike("name", product).limit(1).execute().data
    if not r:
        return {"found": False, "product": product}
    p = r[0]
    return {"found": True, "product_id": p["id"], "name": p["name"], "unit": p["unit"],
            "price": p["price"], "stock": p["stock"], "requested": quantity,
            "ok": p["stock"] >= quantity}

@mcp.tool()
def reserve_stock(product_id: str, quantity: float, actor_role: str) -> dict:
    """Atomically deduct stock. Returns reserved=false if stock is insufficient."""
    require_write(actor_role)
    ok = db().rpc("reserve_stock", {"p_product_id": product_id, "p_qty": quantity}).execute().data
    audit(actor_role, "reserve_stock", {"product_id": product_id, "qty": quantity, "reserved": bool(ok)})
    return {"reserved": bool(ok)}

@mcp.tool()
def release_stock(product_id: str, quantity: float, actor_role: str) -> dict:
    """Give stock back (used to roll back a failed approval)."""
    require_write(actor_role)
    db().rpc("release_stock", {"p_product_id": product_id, "p_qty": quantity}).execute()
    audit(actor_role, "release_stock", {"product_id": product_id, "qty": quantity})
    return {"released": True}

if __name__ == "__main__":
    mcp.run()
