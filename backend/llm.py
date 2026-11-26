"""Intent extraction: Kannada/Tamil/Hindi/English text -> validated structured data.
Provider: Gemini (free tier) if GEMINI_API_KEY is set, otherwise Claude (ANTHROPIC_API_KEY)."""
import json, os, time
from typing import Literal, Optional
from pydantic import BaseModel, Field

class Item(BaseModel):
    product: str
    quantity: float = Field(gt=0, le=100000)
    unit: str = "kg"

class Extracted(BaseModel):
    language: Literal["kn", "ta", "hi", "en"]
    intent: Literal["new_order", "check_stock", "other"]
    vendor_name: Optional[str] = None
    items: list[Item] = []

UNIT_TO_KG = {"kg": 1, "kilo": 1, "kilos": 1, "quintal": 100, "ton": 1000, "tonne": 1000, "g": 0.001}

JSON_SHAPE = ('{"language": "kn|ta|hi|en", "intent": "new_order|check_stock|other", '
              '"vendor_name": string or null, '
              '"items": [{"product": "canonical English catalog name", "quantity": number, "unit": "kg|quintal|ton|g"}]}')

def _system(products, vendors):
    catalog = "\n".join(f'- {p["name"]} (also: {", ".join(p["aliases"])})' for p in products)
    vlist = "\n".join(f'- {v["name"]} (also: {", ".join(v["aliases"])})' for v in vendors)
    return ("You extract wholesale requests from messages in Kannada, Tamil, Hindi or English.\n"
            "Map every product to its canonical English catalog name. Use vendor_name exactly as a "
            "known vendor if possible. Never invent items or quantities that are not in the message. "
            "If it is not an order or stock question, use intent 'other'.\n"
            f"Reply with ONLY a JSON object of this shape: {JSON_SHAPE}\n\n"
            f"PRODUCT CATALOG:\n{catalog}\n\nKNOWN VENDORS:\n{vlist}")

def _call_gemini(system: str, text: str) -> dict:
    """Tries each model in GEMINI_MODEL (comma-separated), retrying when Google is busy."""
    from google import genai
    from google.genai import types, errors
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    models = [m.strip() for m in os.getenv("GEMINI_MODEL", "gemini-3.8-flash").split(",") if m.strip()]
    last = None
    for model in models:
        for attempt in range(3):
            try:
                resp = client.models.generate_content(
                    model=model, contents=text,
                    config=types.GenerateContentConfig(system_instruction=system, temperature=0,
                                                       response_mime_type="application/json"))
                return json.loads(resp.text)
            except errors.APIError as e:
                last = e
                if e.code in (429, 500, 503):      # busy / rate limited: wait and retry
                    time.sleep(2 * (attempt + 1))
                    continue
                break                              # e.g. 404 model gone: try next model
    raise RuntimeError(f"AI service is busy or unavailable, please try again in a minute. ({last})")

def _call_claude(system: str, text: str) -> dict:
    import anthropic
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5"), max_tokens=800, system=system,
        messages=[{"role": "user", "content": text}])
    raw = msg.content[0].text.strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(raw)

def extract(text: str, products: list[dict], vendors: list[dict]) -> Extracted:
    system = _system(products, vendors)
    data = _call_gemini(system, text) if os.getenv("GEMINI_API_KEY") else _call_claude(system, text)
    try:
        ex = Extracted(**data)                       # schema validation
    except Exception:
        raise RuntimeError("I could not understand that request. Please rephrase it.")                           # schema validation
    for it in ex.items:                              # normalise units to kg
        it.quantity = round(it.quantity * UNIT_TO_KG.get(it.unit.lower(), 1), 3)
        it.unit = "kg"
    return ex
