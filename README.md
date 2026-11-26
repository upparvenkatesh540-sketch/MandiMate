# MandiMate – voice/text order agent built on MCP (wHACKiest 2026, Track 1)

```
Voice/Text → FastAPI agent (Claude extracts intent) → MCP client → 3 MCP servers → Supabase
                                  ↑ human approval gate in the Next.js dashboard ↓
```
| Deck slide item | Where it lives |
|---|---|
| Inventory / Orders / Notifications MCP servers | `backend/*_server.py` |
| MCP client (tool discovery + routing) | `backend/mcp_hub.py` |
| Intent extraction + schema validation | `backend/llm.py` |
| Approval gate, rollback, idempotency | `backend/main.py`, `orders_server.py` |
| Role-based access, audit trail | `backend/common.py` |
| Atomic stock / confirm logic | `supabase/schema.sql` |
| Dashboard, voice recording, approval UI | `frontend/app/page.js` |

## Setup
1. **Supabase**: create a project → SQL Editor → paste and run `supabase/schema.sql`.
   Copy Project URL and the *service_role* key (Settings → API).
2. **Backend**
   ```bash
   cd backend
   python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env        # fill SUPABASE_URL, SUPABASE_SERVICE_KEY, ANTHROPIC_API_KEY (+ ELEVENLABS_API_KEY optional)
   uvicorn main:app --reload --port 8000
   ```
   Check http://localhost:8000/api/health → lists the 10 discovered MCP tools.
3. **Frontend**
   ```bash
   cd frontend
   cp .env.local.example .env.local
   npm install && npm run dev       # http://localhost:3000
   ```
4. **Demo**: click a sample language button → *Understand* → review → *Approve*.
   Watch stock drop, the vendor balance rise, and the activity log fill.
   Switch role to `viewer` and approve to show the role-based block.

## Demo script (matches the deck's guardrails)
- Normal order in Kannada/Tamil/Hindi/English.
- Ask for 9999 kg tomato → stock warning, nothing drafted.
- Double-click Understand / approve twice → idempotency + "already confirmed".
- Viewer role → blocked. Show the audit log.

## Deploy (AWS)
- Backend: EC2 (t3.small) or App Runner. `uvicorn main:app --host 0.0.0.0 --port 8000` behind HTTPS.
  Set env vars from `.env.example`, and `FRONTEND_ORIGIN` to your frontend URL.
- Frontend: Vercel or AWS Amplify, with `NEXT_PUBLIC_API` set to the backend URL.
  (Browser microphone access requires HTTPS.)

## Known limits / next steps
- WhatsApp is a sandbox adapter: `send_message` logs to the `notifications` table. Replace its body
  with a Twilio/Meta WhatsApp call to go live.
- No real payments; `balance_due` is the ledger. Add a `record_payment` tool on the Orders server next.
- No login: `role` is chosen in the UI for the demo. Use Supabase Auth in production.
- Test voice quality in each language before the demo; the transcript is editable by design.
