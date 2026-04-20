# Operations Guide

## Daily Operations

### Check Service Health
```bash
curl https://sync.integritasmrv.com/health
```

### View Sync Logs
```bash
docker exec dataroom-sync cat /data/sync.db | sqlite3 -header -separator '|'
# Or use the logs
docker logs dataroom-sync --tail 50
```

### View Investor Status
```bash
curl https://sync.integritasmrv.com/api/status/investor@example.com
```

### List Published Documents
```bash
curl https://sync.integritasmrv.com/api/documents/series-a
```

## Mayan EDMS Workflow

1. Upload document to Mayan EDMS
2. Tag document with deal room (e.g., `series-a`, `lender-dd`)
3. Mayan workflow triggers webhook to `/api/mayan/webhook`
4. Sync service pulls document metadata and file
5. Document is uploaded to corresponding Pydio workspace

## DocuSeal Webhook Configuration

1. Log into DocuSeal admin panel
2. Go to Form Settings > Webhooks
3. Add webhook: `https://sync.integritasmrv.com/api/docuseal/webhook`
4. Set secret header: `X-Docuseal-Signature` with value matching `DOCUSEAL_SECRET`
5. Enable events: `form.completed`

## Mayan Workflow Trigger Setup

1. Log into Mayan EDMS admin
2. Navigate to Workflows > Triggers
3. Create new trigger for `document_create` and `document_update` events
4. Set action to webhook POST to `https://sync.integritasmrv.com/api/mayan/webhook`
5. Include `document_id` in payload

## Troubleshooting

### Sync service not responding
```bash
docker-compose -f /opt/investor-dataroom/sync/docker-compose.yml restart
```

### Check container logs
```bash
docker logs -f dataroom-sync
```

### Verify network connectivity
```bash
docker exec dataroom-sync ping mayan-app
docker exec dataroom-sync ping pydio-cells
```

### Reset investor access
```bash
# Connect to sync database
docker exec -it dataroom-sync sqlite3 /data/sync.db
# Update investor status
UPDATE investors SET pydio_access_granted = 0 WHERE email = 'investor@example.com';
```

## Database Schema

### published table
- `mayan_id` - Mayan document ID
- `version` - Document version
- `pydio_path` - Path in Pydio
- `deal_room` - Deal room category
- `published_at` - Publication timestamp
- `revoked_at` - Revocation timestamp (null if active)

### investors table
- `email` - Investor email
- `deal_room` - Assigned deal room
- `nda_signed_at` - NDA signing timestamp
- `pydio_access_granted` - Access granted flag (0/1)