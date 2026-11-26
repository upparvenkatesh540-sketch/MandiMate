"""Shared helpers for all MCP servers: DB client, role check, audit trail."""
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
_db = None

def db():
    global _db
    if _db is None:
        _db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    return _db

WRITE_ROLES = {"owner", "staff"}   # "viewer" is read-only

def require_write(role: str):
    if role not in WRITE_ROLES:
        raise ValueError(f"Role '{role}' is not allowed to perform this action")

def audit(actor: str, action: str, detail: dict):
    db().table("audit_log").insert({"actor": actor, "action": action, "detail": detail}).execute()
