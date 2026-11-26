"""FastAPI agent: text/voice -> LLM extraction -> MCP tool calls -> human approval."""
import asyncio, os
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from common import db, audit
from llm import extract
from mcp_hub import MCPHub

hub = MCPHub()

@asynccontextmanager
async def lifespan(app):
    await hub.start()
    yield
    await hub.stop()

app = FastAPI(title="MandiMate Agent", lifespan=lifespan)
app.add_middleware(CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")],
    allow_methods=["*"], allow_headers=["*"])

@app.exception_handler(RuntimeError)          # errors raised by MCP tools (role, state...)
async def mcp_error(_, exc):
    return JSONResponse({"detail": str(exc)}, status_code=400)

class ParseIn(BaseModel):
    text: str
    request_id: str            # idempotency key, one per submission from the UI
    role: str = "owner"

class OrderIn(BaseModel):
    order_id: str
    role: str = "owner"

@app.get("/api/health")
def health():
    return {"ok": True, "tools": sorted(hub.tools)}

@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)):
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        raise HTTPException(503, "Voice service not configured - please type your request")
    audio = await file.read()
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post("https://api.elevenlabs.io/v1/speech-to-text",
            headers={"xi-api-key": key}, data={"model_id": "scribe_v1"},
            files={"file": (file.filename or "voice.webm", audio, file.content_type or "audio/webm")})
    if r.status_code != 200:
        raise HTTPException(502, "Speech service error - please type your request")
    j = r.json()
    return {"text": j.get("text", ""), "language": j.get("language_code")}

@app.post("/api/parse")
async def parse(body: ParseIn):
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Empty request")
    products = db().table("products").select("name,aliases").execute().data
    vendors = db().table("vendors").select("name,aliases").execute().data
    ex = await asyncio.to_thread(extract, text, products, vendors)
    audit(body.role, "parse", {"text": text, "extracted": ex.model_dump()})

    if ex.intent == "other" or not ex.items:
        return {"kind": "clarify", "message": "I couldn't find an order or stock question. Please rephrase."}

    # Context-aware: check stock for every line via the Inventory MCP server
    lines, warnings = [], []
    for it in ex.items:
        s = await hub.call("check_stock", product=it.product, quantity=it.quantity)
        if not s["found"]:
            warnings.append(f"'{it.product}' is not in the catalog - skipped")
        elif not s["ok"]:
            warnings.append(f"{s['name']}: asked {it.quantity:g} kg but only {s['stock']:g} kg in stock - skipped")
        else:
            lines.append({"product_id": s["product_id"], "quantity": it.quantity, "name": s["name"], "stock": s["stock"]})

    if ex.intent == "check_stock":
        return {"kind": "stock", "lines": lines, "warnings": warnings, "language": ex.language}

    if not ex.vendor_name:
        return {"kind": "clarify", "message": "Which vendor is this order for?", "warnings": warnings}
    vendor = await hub.call("find_vendor", name=ex.vendor_name)
    if not vendor["found"]:
        return {"kind": "clarify", "message": f"Vendor '{ex.vendor_name}' not found.", "warnings": warnings}
    if not lines:
        return {"kind": "clarify", "message": "No item could be added to the order.", "warnings": warnings}

    draft = await hub.call("draft_order", vendor_id=vendor["vendor_id"],
        items=[{"product_id": l["product_id"], "quantity": l["quantity"]} for l in lines],
        source_text=text, language=ex.language, idempotency_key=body.request_id, actor_role=body.role)
    order = await hub.call("get_order", order_id=draft["order_id"])
    return {"kind": "proposal", "order": order, "warnings": warnings, "language": ex.language}

@app.post("/api/approve")
async def approve(body: OrderIn):
    order = await hub.call("get_order", order_id=body.order_id)
    if order["status"] != "draft":
        raise HTTPException(409, f"Order is already {order['status']}")
    reserved = []
    try:
        for it in order["order_items"]:
            r = await hub.call("reserve_stock", product_id=it["product_id"],
                               quantity=it["quantity"], actor_role=body.role)
            if not r["reserved"]:
                raise HTTPException(409, f"Not enough stock for {it['products']['name']}")
            reserved.append(it)
        await hub.call("confirm_order", order_id=body.order_id, actor_role=body.role)
    except Exception:
        for it in reserved:                                   # roll back
            await hub.call("release_stock", product_id=it["product_id"],
                           quantity=it["quantity"], actor_role=body.role)
        raise
    msg = await hub.call("prepare_message", order_id=body.order_id)
    await hub.call("send_message", order_id=body.order_id, body=msg["text"], actor_role=body.role)
    return {"status": "confirmed", "message": msg["text"]}

@app.post("/api/cancel")
async def cancel(body: OrderIn):
    return await hub.call("cancel_order", order_id=body.order_id, actor_role=body.role)

@app.get("/api/dashboard")
def dashboard():
    d = db()
    return {
        "products": d.table("products").select("name,unit,price,stock").order("name").execute().data,
        "vendors": d.table("vendors").select("name,language,balance_due").order("name").execute().data,
        "orders": d.table("orders").select("id,status,total,created_at,vendors(name)")
                   .order("created_at", desc=True).limit(10).execute().data,
        "audit": d.table("audit_log").select("id,actor,action,detail,created_at")
                   .order("id", desc=True).limit(15).execute().data,
    }
