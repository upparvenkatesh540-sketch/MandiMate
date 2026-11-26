import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
c = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
for m in ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"]:
    try:
        r = c.models.generate_content(model=m, contents="Say OK")
        print(m, "-> WORKS:", r.text.strip()[:20])
    except Exception as e:
        print(m, "-> ERROR:", str(e)[:150])