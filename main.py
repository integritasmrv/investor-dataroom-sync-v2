import os, asyncio
import httpx
import sqlite3
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI(title="Investor Data Room Sync Service", version="2.0")

MAYAN_URL = os.environ.get("MAYAN_URL", "http://144.91.126.111:8010")
MAYAN_USER = os.environ.get("MAYAN_USER", "admin")
MAYAN_PASS = os.environ.get("MAYAN_PASS", "password")
PYDIO_URL = os.environ.get("PYDIO_URL", "http://144.91.126.111:18081")
PYDIO_TOKEN = os.environ.get("PYDIO_TOKEN", "token")
DOCUSEAL_SECRET = os.environ.get("DOCUSEAL_SECRET", "secret")
DB_PATH = "/data/sync.db"

DEAL_ROOM_MAPPING = {
    "series-a": "Series A Documents",
    "lender-dd": "Lender Due Diligence",
    "board-only": "Board Materials",
    "general-investors": "General Investor Materials"
}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS published (
        mayan_id TEXT, version TEXT, pydio_path TEXT, deal_room TEXT,
        published_at TEXT, revoked_at TEXT, PRIMARY KEY (mayan_id, version)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS investors (
        email TEXT PRIMARY KEY, deal_room TEXT, nda_signed_at TEXT, pydio_access_granted INTEGER DEFAULT 0
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sync_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, event TEXT, details TEXT
    )""")
    conn.commit()
    conn.close()

def log_event(event: str, details: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO sync_log (timestamp, event, details) VALUES (?,?,?)",
                 (datetime.utcnow().isoformat(), event, details))
    conn.commit()
    conn.close()

def get_mayan_documents():
    resp = httpx.get(f"{MAYAN_URL}/api/v4/documents/", timeout=30)
    resp.raise_for_status()
    return resp.json().get("results", [])

def get_mayan_document_metadata(doc_id: str):
    resp = httpx.get(f"{MAYAN_URL}/api/v4/documents/{doc_id}/", timeout=30)
    resp.raise_for_status()
    return resp.json()

def pydio_create_folder(path: str):
    folder_name = path.split("/")[-1]
    parent_path = "/".join(path.split("/")[:-1]) if "/" in path else "/"
    payload = {"Path": parent_path, "FolderTitle": folder_name, "Recursive": "false"}
    resp = httpx.post(f"{PYDIO_URL}/a/acl/mkdir",
                      headers={"Authorization": f"Bearer {PYDIO_TOKEN}"},
                      json=payload, timeout=30)
    return resp.status_code in (200, 201, 409)

def pydio_upload_file(workspace: str, folder_path: str, filename: str, content: bytes) -> bool:
    files = {"file": (filename, content)}
    data = {"folderPath": folder_path}
    resp = httpx.post(f"{PYDIO_URL}/a/fs/move",
                      headers={"Authorization": f"Bearer {PYDIO_TOKEN}"},
                      files=files, data=data, timeout=60)
    return resp.status_code in (200, 201)

def pydio_share_file(workspace: str, file_path: str, email: str) -> str:
    payload = {
        "Workspace": workspace, "FilePath": file_path,
        "ShareType": "link", "SharePolicy": {"allowExternal": False, "requireCredentials": True}
    }
    resp = httpx.post(f"{PYDIO_URL}/a/shares/create",
                      headers={"Authorization": f"Bearer {PYDIO_TOKEN}"},
                      json=payload, timeout=30)
    if resp.status_code == 200:
        return resp.json().get("share_url", "")
    return ""

def pydio_grant_workspace_access(email: str, workspace: str):
    payload = {"UserEmail": email, "WorkspaceSlug": workspace}
    resp = httpx.post(f"{PYDIO_URL}/a/acl/workspace/add-user",
                      headers={"Authorization": f"Bearer {PYDIO_TOKEN}"},
                      json=payload, timeout=30)
    return resp.status_code == 200

@app.on_event("startup")
async def startup():
    init_db()

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "dataroom-sync", "version": "2.0"}

@app.post("/api/publish")
async def publish(request: Request):
    data = await request.json()
    document_id = data.get("document_id")
    version = data.get("version", "latest")
    deal_room = data.get("deal_room", "general-investors")

    if not document_id:
        raise HTTPException(status_code=400, detail="document_id required")

    log_event("publish_started", f"doc_id={document_id}, deal_room={deal_room}")

    try:
        doc_meta = get_mayan_document_metadata(document_id)
        filename = doc_meta.get("label", f"doc_{document_id}")
        folder_path = f"/{DEAL_ROOM_MAPPING.get(deal_room, deal_room)}"
        pydio_create_folder(folder_path)

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(f"{MAYAN_URL}/media/documents/{document_id}/")
            if resp.status_code == 200:
                file_content = resp.content
            else:
                file_content = b"placeholder"

        if pydio_upload_file(deal_room, folder_path, filename, file_content):
            pydio_path = f"{folder_path}/{filename}"
            conn = sqlite3.connect(DB_PATH)
            conn.execute("""INSERT OR REPLACE INTO published
                           (mayan_id, version, pydio_path, deal_room, published_at)
                           VALUES (?,?,?,?,?)""",
                        (document_id, version, pydio_path, deal_room, datetime.utcnow().isoformat()))
            conn.commit()
            conn.close()
            log_event("publish_completed", f"pydio_path={pydio_path}")
            return {"status": "published", "pydio_path": pydio_path, "document_id": document_id}

        raise HTTPException(status_code=500, detail="Failed to upload to Pydio")

    except Exception as e:
        log_event("publish_failed", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/docuseal/webhook")
async def docuseal_webhook(request: Request):
    signature = request.headers.get("X-Docuseal-Signature", "")
    if signature != DOCUSEAL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    data = await request.json()
    event_type = data.get("event_type")

    if event_type != "form.completed":
        return {"status": "ignored", "event": event_type}

    form_data = data.get("data", {})
    email = form_data.get("submitters", [{}])[0].get("email", "")
    form_id = form_data.get("form_id", "")
    deal_room = form_data.get("external_id", "series-a")

    if not email:
        raise HTTPException(status_code=400, detail="No email found")

    log_event("nda_signed", f"email={email}, form_id={form_id}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""INSERT OR REPLACE INTO investors
                   (email, deal_room, nda_signed_at, pydio_access_granted)
                   VALUES (?,?,?,0)""",
                (email, deal_room, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

    workspace = deal_room.replace("_", "-")
    try:
        pydio_grant_workspace_access(email, workspace)
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE investors SET pydio_access_granted=1 WHERE email=?", (email,))
        conn.commit()
        conn.close()
        log_event("access_granted", f"email={email}, workspace={workspace}")
    except Exception as e:
        log_event("access_grant_failed", str(e))

    return {"status": "processed", "email": email}

@app.post("/api/mayan/webhook")
async def mayan_webhook(request: Request):
    data = await request.json()
    document_id = str(data.get("document_id", ""))
    event = data.get("event", "")
    log_event("mayan_webhook", f"doc_id={document_id}, event={event}")
    if event in ("document_created", "document_updated"):
        return {"status": "queued", "document_id": document_id}
    return {"status": "ignored"}

@app.get("/api/status/{email}")
async def investor_status(email: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("SELECT * FROM investors WHERE email=?", (email,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Investor not found")
    return {"email": row[0], "deal_room": row[1], "nda_signed_at": row[2], "pydio_access_granted": bool(row[3])}

@app.get("/api/documents/{deal_room}")
async def list_documents(deal_room: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("SELECT mayan_id, version, pydio_path, published_at FROM published WHERE deal_room=?", (deal_room,))
    rows = cursor.fetchall()
    conn.close()
    return {"deal_room": deal_room, "documents": [
        {"mayan_id": r[0], "version": r[1], "pydio_path": r[2], "published_at": r[3]}
        for r in rows
    ]}

@app.get("/api/mayan/list")
async def list_mayan_documents():
    try:
        docs = get_mayan_documents()
        return {"documents": [{"id": d.get("id"), "label": d.get("label")} for d in docs]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)