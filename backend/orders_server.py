"""Orders MCP server: vendor lookup and the draft -> confirmed/cancelled lifecycle."""
from mcp.server.fastmcp import FastMCP
from common import db, require_write, audit

mcp = FastMCP("orders")
ORDER_SELECT = ("*, vendors(name,language,phone), "
                "order_items(product_id, quantity, unit_price, products(name,unit))")

@mcp.tool()
def find_vendor(name: str) -> dict:
    """Find a vendor by name or alias (any language, case-insensitive substring)."""
    q = name.strip().lower()
    for v in db().table("vendors").select("*").execute().data:
        names = [v["name"].lower()] + [a.lower() for a in v["aliases"]]
        if any(q in n or n in q for n in names):
            return {"found": True, "vendor_id": v["id"], "name": v["name"],
                    "language": v["language"], "phone": v["phone"]}
    return {"found": False, "query": name}

@mcp.tool()
def draft_order(vendor_id: str, items: list[dict], source_text: str, language: str,
                idempotency_key: str, actor_role: str) -> dict:
    """Create a DRAFT order. items = [{product_id, quantity}]. Prices and total are
    computed server-side. Repeating the same idempotency_key returns the same order."""
    require_write(actor_role)
    dup = db().table("orders").select("id").eq("idempotency_key", idempotency_key).execute().data
    if dup:
        return {"order_id": dup[0]["id"], "duplicate": True}
    ids = [i["product_id"] for i in items]
    prices = {p["id"]: p["price"] for p in
              db().table("products").select("id,price").in_("id", ids).execute().data}
    if len(prices) != len(set(ids)):
        raise ValueError("Unknown product in order")
    total = sum(prices[i["product_id"]] * float(i["quantity"]) for i in items)
    order = db().table("orders").insert({
        "vendor_id": vendor_id, "total": total, "idempotency_key": idempotency_key,
        "source_text": source_text, "language": language}).execute().data[0]
    db().table("order_items").insert([
        {"order_id": order["id"], "product_id": i["product_id"],
         "quantity": float(i["quantity"]), "unit_price": prices[i["product_id"]]} for i in items
    ]).execute()
    audit(actor_role, "draft_order", {"order_id": order["id"], "total": total})
    return {"order_id": order["id"], "duplicate": False}

@mcp.tool()
def get_order(order_id: str) -> dict:
    """Return an order with vendor and line items."""
    return db().table("orders").select(ORDER_SELECT).eq("id", order_id).single().execute().data

@mcp.tool()
def confirm_order(order_id: str, actor_role: str) -> dict:
    """Atomically confirm a draft order and add its total to the vendor's balance due."""
    require_write(actor_role)
    ok = db().rpc("confirm_order_tx", {"p_order_id": order_id}).execute().data
    if not ok:
        raise ValueError("Order is not in draft state")
    audit(actor_role, "confirm_order", {"order_id": order_id})
    return {"confirmed": True}

@mcp.tool()
def cancel_order(order_id: str, actor_role: str) -> dict:
    """Cancel a draft order."""
    require_write(actor_role)
    db().table("orders").update({"status": "cancelled"}).eq("id", order_id).eq("status", "draft").execute()
    audit(actor_role, "cancel_order", {"order_id": order_id})
    return {"cancelled": True}

if __name__ == "__main__":
    mcp.run()
