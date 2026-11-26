"""Notifications MCP server: localized vendor messages. WhatsApp is a sandbox adapter
(logs to the notifications table); swap send_message's body for Twilio/Meta later."""
from mcp.server.fastmcp import FastMCP
from common import db, require_write, audit

mcp = FastMCP("notifications")
ORDER_SELECT = "*, vendors(name,language,phone), order_items(quantity, products(name,unit))"

TEMPLATES = {
    "en": "Hi {v}, your order #{n} is confirmed: {lines}. Total ₹{t}.",
    "hi": "नमस्ते {v}, आपका ऑर्डर #{n} कन्फ़र्म हो गया: {lines}। कुल ₹{t}।",
    "kn": "ನಮಸ್ಕಾರ {v}, ನಿಮ್ಮ ಆರ್ಡರ್ #{n} ದೃಢೀಕರಿಸಲಾಗಿದೆ: {lines}. ಒಟ್ಟು ₹{t}.",
    "ta": "வணக்கம் {v}, உங்கள் ஆர்டர் #{n} உறுதி செய்யப்பட்டது: {lines}. மொத்தம் ₹{t}.",
}

def _num(x):
    x = float(x)
    return int(x) if x.is_integer() else x

@mcp.tool()
def prepare_message(order_id: str) -> dict:
    """Build the confirmation message in the vendor's preferred language."""
    o = db().table("orders").select(ORDER_SELECT).eq("id", order_id).single().execute().data
    lang = o["vendors"]["language"]
    lines = ", ".join(f'{i["products"]["name"]} {_num(i["quantity"])} {i["products"]["unit"]}'
                      for i in o["order_items"])
    text = TEMPLATES.get(lang, TEMPLATES["en"]).format(
        v=o["vendors"]["name"], n=order_id[:8], lines=lines, t=_num(o["total"]))
    return {"text": text, "language": lang, "phone": o["vendors"]["phone"]}

@mcp.tool()
def send_message(order_id: str, body: str, actor_role: str, channel: str = "whatsapp") -> dict:
    """Send (sandbox: log) a message to the order's vendor."""
    require_write(actor_role)
    o = db().table("orders").select("vendor_id").eq("id", order_id).single().execute().data
    db().table("notifications").insert({"order_id": order_id, "vendor_id": o["vendor_id"],
        "channel": channel, "body": body, "status": "sandbox_logged"}).execute()
    audit(actor_role, "send_message", {"order_id": order_id, "channel": channel})
    return {"sent": True, "mode": "sandbox"}

if __name__ == "__main__":
    mcp.run()
