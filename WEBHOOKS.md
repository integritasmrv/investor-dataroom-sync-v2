# Investor Data Room - Webhook Configuration Guide

## Target Endpoints
- Health: https://sync.integritasmrv.com/health
- DocuSeal: https://sync.integritasmrv.com/webhook/docuseal
- Publish: https://sync.integritasmrv.com/publish

## 1. DocuSeal -> Sync Webhook

### DocuSeal Admin Setup
1. Login to https://sign.integritasmrv.com/admin
2. Go to Settings > Webhooks > Add Webhook
3. Configure:
   - URL: https://sync.integritasmrv.com/webhook/docuseal
   - Events: form.completed
   - Secret: DataroalDocuSeal2026Webhook

## 2. Mayan -> Sync Publish Trigger

### Mayan Admin Setup
1. Go to Settings > Document States
2. Create/edit state: investor_ready
3. Add workflow action HTTP POST to sync service

## 3. Pydio Pre-Requisites

### Required Workspaces
- series-a
- lender-dd
- board-only
- general-investors

## 4. NDA to Cell Mapping
- Series A NDA -> series-a
- Lender DD NDA -> lender-dd
- Board NDA -> board-only
- Default -> general-investors

## 5. Retry Rules
- 3 attempts, exponential backoff (1s, 2s, 4s)

## 6. Idempotency
- processed_events table tracks event_id