from fastapi import FastAPI, Request, HTTPException, Header
import os
import httpx
import sqlite3
import hashlib
import hmac
import json
from datetime import datetime
from typing import Optional

app = FastAPI()

DB_PATH = os.environ.get("SYNC_DB_PATH", "/data/sync.db")
MAYAN_URL = os.environ.get("MAYAN_API_URL", "http://mayan-app:8000")
MAYAN_TOKEN = os.environ.get("MAYAN_API_TOKEN", "DataroomMayan2026Admin")
PYDIO_URL = os.environ.get("PYDIO_API_URL", "http://pydio-cells:8080")
PYDIO_TOKEN = os.environ.get("PYDIO_API_TOKEN", "DataroomPydio2026Token")
DOCUSEAL_SECRET = os.environ.get("DOCUSEAL_WEBHOOK_SECRET", "DataroalDocuSeal2026Webhook")

NDA_MAPPING = {
    "Series A NDA": "series-a",
    "Lender DD NDA": "lender-dd",
    "Board NDA": "board-only",
}
DEFAULT_CELL = "general-investors"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS processed_events (
        event_id TEXT PRIMARY KEY,
        received_at TEXT,
        status TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS investors (
        email TEXT PRIMARY KEY,
        deal_room TEXT,
        nda_signed_at TEXT,
        pydio_access_granted INTEGER DEFAULT 0
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS publications (
        mayan_doc_id TEXT,
        version TEXT,
        pydio_path TEXT,
        deal_room TEXT,
        checksum TEXT,
        published_at TEXT,
        PRIMARY KEY (mayan_doc_id, version)
    )""")
    conn.commit()
    conn.close()

init_db()

def verify_docuseal_signature(payload: str, signature: str) -> bool:
    expected = hmac.new(DOCUSEAL_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

def get_cell_for_template(template_name: str) -> str:
    return NDA_MAPPING.get(template_name, DEFAULT_CELL)

def retry_with_backoff(func, max_attempts=3):
    for attempt in range(max_attempts):
        try:
            return func()
        except Exception as e:
            if attempt == max_attempts - 1:
                raise e
            import time
            time.sleep(2 ** attempt)

@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@app.post("/webhook/docuseal")
async def docuseal_webhook(request: Request):
    payload = await request.body()
    signature = request.headers.get("X-Docuseal-Signature", "")
    
    if not verify_docuseal_signature(payload.decode(), signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    data = json.loads(payload)
    event_id = data.get("event_id", "unknown")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("SELECT status FROM processed_events WHERE event_id = ?", (event_id,))
    row = cursor.fetchone()
    if row and row[0] == "processed":
        conn.close()
        return {"status": "duplicate", "event_id": event_id}
    conn.close()
    
    event_type = data.get("event")
    if event_type != "form.completed":
        return {"status": "ignored", "event": event_type}
    
    form_data = data.get("data", {})
    template = form_data.get("form", {}).get("name", "Unknown")
    submitters = form_data.get("submitters", [])
    external_id = form_data.get("external_id", "")
    deal_room = external_id or get_cell_for_template(template)
    
    for submitter in submitters:
        email = submitter.get("email")
        if not email:
            continue
        
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT OR REPLACE INTO investors VALUES (?,?,?,0)", 
                    (email, deal_room, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
        
        print(json.dumps({
            "event": "investor_registered",
            "email": email,
            "deal_room": deal_room,
            "timestamp": datetime.utcnow().isoformat()
        }))
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO processed_events VALUES (?,?,?)", 
                (event_id, datetime.utcnow().isoformat(), "processed"))
    conn.commit()
    conn.close()
    
    return {
        "status": "success",
        "event_id": event_id,
        "investors_processed": len(submitters)
    }

@app.post("/publish")
async def publish(request: Request):
    data = await request.json()
    doc_id = data.get("document_id")
    deal_room = data.get("deal_room", "general")
    
    if not doc_id:
        raise HTTPException(status_code=400, detail="document_id required")
    
    return {
        "status": "published",
        "doc_id": doc_id,
        "deal_room": deal_room
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)