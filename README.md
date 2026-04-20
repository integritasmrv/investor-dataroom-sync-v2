# Investor Data Room Sync Service

Webhook-based integration service connecting Mayan EDMS, DocuSeal, and Pydio Cells for investor data room operations.

## Architecture

```
DocuSeal (e-signatures) --> Sync Service --> Pydio Cells (data room)
                                    |
Mayan EDMS (documents) ---------------|
```

## Services

- **Mayan EDMS**: Document management at `mayan.integritasmrv.com`
- **DocuSeal**: E-signatures at `sign.integritasmrv.com`
- **Pydio Cells**: Data room at `dataroom.integritasmrv.com`
- **Sync Service**: Integration hub at `sync.integritasmrv.com`

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service health check |
| `/api/publish` | POST | Publish document from Mayan to Pydio |
| `/api/docuseal/webhook` | POST | Handle DocuSeal NDA completion |
| `/api/mayan/webhook` | POST | Handle Mayan document events |
| `/api/status/{email}` | GET | Get investor status |
| `/api/documents/{deal_room}` | GET | List published documents |

## Setup

```bash
cp .env.example .env
# Edit .env with actual credentials
docker-compose up -d
```

## Deal Rooms

- `series-a` - Series A Documents
- `lender-dd` - Lender Due Diligence
- `board-only` - Board Materials
- `general-investors` - General Investor Materials

## Environment Variables

| Variable | Description |
|----------|-------------|
| `MAYAN_URL` | Mayan EDMS URL (default: http://mayan-app:8000) |
| `MAYAN_USER` | Mayan admin username |
| `MAYAN_PASS` | Mayan admin password |
| `PYDIO_URL` | Pydio Cells URL (default: http://pydio-cells:8080) |
| `PYDIO_TOKEN` | Pydio API token |
| `DOCUSEAL_SECRET` | DocuSeal webhook secret |