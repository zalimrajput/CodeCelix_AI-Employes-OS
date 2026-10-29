# AI Employee OS — Current System Setup

**Snapshot date:** 2026-10-28 · **App:** AI Employee OS · **Env:** development (local: backend `:8000`, frontend `:3000`)

This document catalogs the current, verified state of every moving part: LLM routing, AI agents, AI tools, external integrations, background workers, and workflows. It is updated whenever the system changes.

---

## 1. System Overview

```
Browser (Next.js :3000)
   │  Supabase JWT + HTTPS
   ▼
FastAPI backend (:8000, uvicorn --reload)
   ├── API routers  (app/api/v1/**)
   ├── AI engine    (app/ai/**)      → model_router → Google Gemini (OpenRouter optional)
   ├── Integrations (app/integrations/**)  → OAuth + env-key provider clients
   ├── Services     (app/services/**)      → workflow_service, email_service, …
   └── Workers      (workers/**)           → Celery + Redis (REDIS_URL)
   │
   └── Postgres / Supabase (DATABASE_URL) — multi-tenant RLS via current_org_id()
```

- **Frontend:** Next.js (App Router) + React Query + shadcn-style UI.
- **Backend:** FastAPI, SQLAlchemy, per-org tenancy enforced by RLS + `organization_id` filters.
- **LLM:** Gemini 3.5 Flash (default) → Gemini 3.5 Flash Lite → Gemini 3.1 Flash Lite (fallbacks); OpenRouter optional when `OPENROUTER_API_KEY` is set.
- **Workers:** Celery (`celery -A workers.celery_app worker`), Redis broker.
- **Docs index:** `ARCHITECTURE.md`, `API_SPEC.md`, `INTEGRATION_SETUP.md`, `DASHBOARD_MATRIX.md` (agents & roles → dashboards), `PRD.md`, `CURRENT_STATE.md`, `MEMORY.md`.

---

## 2. LLM & Model Routing (`backend/app/ai/model_router.py`)

| Setting | Value (`.env`) | Purpose |
|---|---|---|
| `DEFAULT_AI_MODEL` | `gemini-3.5-flash` | Default completion model (fast, vision-capable) |
| `AI_MODEL_FALLBACKS` | `gemini-3.5-flash-lite,gemini-3.1-flash-lite` | Chain of fallback models on provider failure |
| `AI_MAX_TOKENS` | `1024` | Caps requests within free-tier limits |
| `OPENROUTER_API_KEY` / `OPENROUTER_BASE_URL` | optional (unset in dev) | Widens the fallback pool when configured (OpenRouter catalog ids incl. `:free`) |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_AI_KEY` | optional | Direct-provider fallbacks when model id implies provider |
| `EMBEDDING_DIMENSION` | `1536` | pgvector dimension (pinned for Gemini output) |
| `GOOGLE_EMBEDDING_MODEL` | `gemini-embedding-001` | Embeddings provider when OpenAI key absent |

**Behavior**
- Model chain: requested/default model first, then every `AI_MODEL_FALLBACKS` entry; provider-side failures (`402/429/5xx`) move to the next model; unknown model ids fall through too.
- **Image / screenshot understanding:** OpenAI-style `image_url` parts convert to Gemini `inlineData` for chat, tool-calling, and streaming — attach up to 4 images (≤5 MB each) in chat.
- **Embeddings:** OpenAI `text-embedding-3-small` when `OPENAI_API_KEY` set, else Google `gemini-embedding-001` (batched, retried); neither → keyword fallback so RAG still works offline.
- Guardrails (`app/ai/guardrails.py`): a safe-tool allowlist (`_SAFE_TOOL_NAMES`) blocks dangerous tool calls.
- **Auth:** the backend verifies Supabase JWTs three-path (`app/core/auth.py`): offline HS256 vs `SUPABASE_JWT_SECRET` → fallback to the project's JWKS endpoint (ES256/RS256 asymmetric keys, what current Supabase projects sign with) → live GoTrue `GET /auth/v1/user` when no secret is set.
- **Model ids go stale:** Google retires old models (e.g. `gemini-2.5-flash/pro` now 404). Both `.env` and the per-row `ai_employees.model` column must point at models that still respond.

---

## 3. AI Agents (`backend/app/ai/agents/`)

Registry: `ALL_AGENTS` (12 specialists + master) plus the `general` default, `resolve_agent(role)` picks by exact role match then synonyms. The **Master Coordinator** plans multi-step work and delegates to specialists via `delegate_task`; it can also send email directly.

| Key | Display | Role | Tools (count) |
|---|---|---|---|
| `sales` | Sales Agent | Sales Manager | 25 |
| `support` | Customer Support | Customer Support | 7 |
| `hr` | HR Assistant | HR Manager | 5 |
| `recruiter` | Recruiter | Recruiter | 6 |
| `finance` | Finance Manager | Finance Manager | 4 |
| `accountant` | AI Accountant | Accountant | 24 |
| `marketing` | Marketing Manager | Marketing Manager | 5 |
| `content_writer` | Content Writer | Content Writer | 3 |
| `legal` | Legal Assistant | Legal | 4 |
| `inventory` | Inventory Manager | Operations Manager | 4 |
| `procurement` | Procurement Manager | Procurement Manager | 3 |
| `executive` | Executive Assistant | CEO / Executive | 17 |
| `master` | AI Manager | Master Coordinator | 3 |
| `general` (default) | AI Employee | General Assistant | 5 |

### Allowed tools per agent
- **sales (25):** search_crm, get_customer, create_customer, list_leads, list_deals, create_activity, summarize_customer, list_quotations, create_reminder, list_reminders, create_meeting, list_meetings, summarize_meeting, transcribe_meeting_audio, send_email, send_quotation_email, submit_quotation_for_approval, classify_email_thread, summarize_email_thread, zoho_create_lead, zoho_create_customer, zoho_list_leads, drive_upload_file, sheets_append_row, slack_post_message
- **support (7):** search_crm, get_customer, summarize_customer, list_tasks, create_activity, classify_email_thread, summarize_email_thread
- **hr (5):** search_crm, list_employees, list_leave_requests, create_task, generate_productivity_report
- **recruiter (6):** search_crm, list_candidates, create_task, create_meeting, summarize_meeting, transcribe_meeting_audio
- **finance (4):** list_invoices, get_invoice, list_expenses, create_invoice
- **accountant (24):** create_invoice, get_invoice, list_invoices, list_expenses, create_expense, create_quotation, list_quotations, generate_quotation_pdf_tool, generate_invoice_pdf_tool, mark_invoice_paid, generate_invoice_payment_link, send_quotation_email, approve_quotation, reject_quotation, generate_revenue_report, generate_expense_report, generate_sales_pipeline_report, generate_productivity_report, generate_forecast_report, generate_customer_cohort_report, xero_create_invoice, xero_list_invoices, onedrive_upload_file, onedrive_append_excel
- **marketing (5):** search_crm, list_campaigns, create_task, create_email_draft, send_email
- **content_writer (3):** create_email_draft, search_knowledge, list_campaigns
- **legal (4):** search_knowledge, get_document, analyze_document, search_crm
- **inventory (4):** search_crm, list_inventory, list_suppliers, create_task
- **procurement (3):** list_purchase_orders, list_suppliers, create_task
- **executive (17):** slack_post_message, search_crm, list_tasks, send_email, create_meeting, summarize_meeting, transcribe_meeting_audio, search_knowledge, get_document, approve_quotation, reject_quotation, generate_revenue_report, generate_expense_report, generate_sales_pipeline_report, generate_productivity_report, generate_forecast_report, generate_customer_cohort_report
- **master (3):** delegate_task, send_email, send_quotation_email
- **general / default (5):** search_crm, get_customer, list_tasks, search_knowledge, get_document

---

## 4. AI Tools — full registry (61 tools, `backend/app/ai/tools/`)

### CRM (`crm_tools.py`)
| Tool | Purpose |
|---|---|
| search_crm | Search customers & leads by name/email/company |
| get_customer | Fetch one customer |
| list_leads | List leads (optionally by status) |
| list_deals | List deals (optionally by stage) |
| create_activity | Log an activity/note on a CRM target |
| summarize_customer | Relationship summary + health assessment |
| create_customer | Create a new CRM customer |

### Email (`email_tools.py`)
| Tool | Purpose |
|---|---|
| send_email | Real email from the org's connected Gmail |
| send_quotation_email | Generate quotation PDF + send as attachment |

### Marketing (`marketing_tools.py`)
| Tool | Purpose |
|---|---|
| list_campaigns | List campaigns by status |
| create_email_draft | Draft an AI email (or in a thread) |
| classify_email_thread | Urgency + category classification |
| summarize_email_thread | Persist a 2–4 sentence thread summary |

### Tasks / Meetings (`task_tools.py`, `reminder_tools.py`, `calendar_tools.py`)
| Tool | Purpose |
|---|---|
| list_tasks / create_task | Task list / create (AI-created) |
| list_meetings / create_meeting | Meeting list / schedule |
| summarize_meeting | Summarize notes → summary + action items + decisions |
| transcribe_meeting_audio | Transcribe uploaded meeting audio |
| create_reminder / list_reminders | Follow-up reminders on records |

### HR (`hr_tools.py`)
| Tool | Purpose |
|---|---|
| list_employees | Human employees |
| list_leave_requests | Leave requests by status |
| list_candidates | Job candidates + AI scores |

### Invoices / Finance (`invoice_tools.py`)
| Tool | Purpose |
|---|---|
| create_invoice / get_invoice / list_invoices | Invoice lifecycle |
| create_expense / list_expenses | Expense records |
| create_quotation / list_quotations | Quotation lifecycle |
| generate_quotation_pdf_tool / generate_invoice_pdf_tool | Branded PDFs |
| mark_invoice_paid | Mark paid + run paid-workflow chain |
| generate_invoice_payment_link | Stripe payment link + QR |
| submit_quotation_for_approval / approve_quotation / reject_quotation | Approval workflow |

### Inventory (`inventory_tools.py`)
| Tool | Purpose |
|---|---|
| list_inventory | Stock levels + low-stock flags |
| list_suppliers | Supplier list |
| list_purchase_orders | Purchase orders by status |

### Knowledge / Documents (`knowledge_tools.py`, `document_tools.py`)
| Tool | Purpose |
|---|---|
| search_knowledge | RAG search over knowledge base |
| get_document | Document metadata + extracted text |
| analyze_document | Contract/NDA/MSA risk analysis |

### Reporting (`reporting_tools.py`)
| Tool | Purpose |
|---|---|
| generate_revenue_report | Aggregates from paid invoices + AI narrative |
| generate_expense_report | Expense aggregates by category |
| generate_sales_pipeline_report | Pipeline value, win rate, stage distribution |
| generate_productivity_report | Per-employee task productivity |
| generate_forecast_report | 3-period moving-average forecast |
| generate_customer_cohort_report | Cohort acquisition/engagement/churn |

### External integrations (`integration_tools.py`)
| Tool | Purpose |
|---|---|
| slack_post_message | Post to connected Slack workspace |
| zoho_create_lead / zoho_create_customer / zoho_list_leads | Mirror leads/customers to and from Zoho CRM |
| xero_create_invoice / xero_list_invoices | Mirror invoices to/from Xero |
| sheets_append_row | Append row / create a Google Sheet |
| drive_upload_file | Upload to connected Google Drive |
| onedrive_upload_file / onedrive_append_excel | OneDrive file upload / Excel table append |

### Delegation (`delegate_tools.py`)
| Tool | Purpose |
|---|---|
| delegate_task | Master → specialist single-task delegation |

---

## 5. External Integrations (13)

### OAuth providers (per-org tokens, encrypted at rest)
Google family (ONE shared callback `/oauth/callback/google`): **gmail**, **google-calendar**, **google-drive**, **google-sheets**
Microsoft family (ONE shared callback `/oauth/callback/microsoft`): **outlook**, **microsoft365**, **onedrive**
Standalone: **slack**, **zoho** (data-center aware: `ZOHO_DATA_CENTER`), **xero** (configurable `XERO_SCOPES`)

### Env-key providers (verified live via `GET /integrations/check/{provider}`)
**whatsapp**, **stripe**, **r2** (Cloudflare R2 / S3 via SigV4)

### Model
- One OAuth client (`.env`) shared by all orgs; each org stores **its own encrypted tokens** in `integrations` (`organization_id`, `provider`, encrypted `access_token`/`refresh_token`, `connected`).
- Auto token refresh on 401 (refresh → re-encrypt → retry once). `save_credentials` preserves the stored refresh token when a refresh payload omits it (regression-fixed 2026-08-12).
- OAuth callback validates the state's org exists (hardened 2026-08-12) and bounces clean errors instead of 500s.
- Status endpoint (`/integrations/status`) reports per-provider configured/connected; env-key "Connected" flags persist in the DB and survive refresh.
- Full setup incl. console URLs: see `INTEGRATION_SETUP.md`.

### Live status (probed read-only, 2026-08-12)

**Google app is published to production** — any new org can now connect Gmail/Calendar/Drive/Sheets with **their own Google account** (no more `access_denied` test-user wall). Verified with a fresh org:

| Org | Connected (with refresh tokens) | Live probe result |
|---|---|---|
| **Zalim lnc** (new org) | gmail, google-calendar, google-drive, google-sheets, zoho, stripe | ✅ **6/6 pass** (calendar fixed — see below) |
| **TechNova Solution** | 13 rows (some predate the offline-access grant) | onedrive, slack, stripe, r2 ✅ · gmail/calendar/drive/outlook/m365/zoho ❌ expired & no refresh — **one-time reconnect required** to mint refresh tokens · xero `invalid_grant` (consumed refresh) · whatsapp test token expired |

**All 13 providers work once each org's OAuth rows carry a refresh token** — the only failing rows are ones connected *before* the `offline_access` grant landed; re-connect once and they self-heal forever. Env-key providers (whatsapp/stripe/r2) are verified live per connection.

Diagnostics: `backend/scripts/_test_all_integrations.py` (re-test all 13), `_diag_refresh.py`.

---

## 6. Dashboards, Human Roles & AI Agents

### Human roles (12) — who lands where, and which agent answers

| Role | Type | Home dashboard (after login) | Default AI agent (chat w/o `?agent=`) |
|---|---|---|---|
| Super Admin | platform | Super Admin Dashboard | master |
| Company Admin | company | Company Admin Dashboard | master |
| CEO / Executive | company | CEO / Executive Dashboard | executive |
| Sales Manager | department | Sales Dashboard | sales |
| Sales Executive | department | Sales Dashboard | sales |
| HR Manager | department | HR Dashboard | hr |
| Finance Manager | department | Finance Dashboard | finance |
| Accountant | department | Finance Dashboard | accountant |
| Customer Support | department | Customer Support Dashboard | support |
| Marketing Manager | department | Marketing Dashboard | marketing |
| Operations Manager | department | Operations Dashboard | inventory |
| Employee / User | personal | Employee Dashboard | per-AI-employee binding |

Legacy rows (`Owner`/`Admin`/`Employee` from migration 0059) map to Company Admin / Company Admin / Employee. **Company Admin + CEO** can open every company dashboard (all 13); **Super Admin** can open all 14 incl. the platform dashboard. Module gating (org admin disables a module) hides the matching dashboards from the nav.

### Dashboards (14) — access matrix + linked AI agent

| # | Dashboard | Route | Roles that can access | AI agent it links to |
|---|---|---|---|---|
| 1 | Super Admin | `/dashboard/super-admin` | Super Admin | master |
| 2 | Company Admin | `/dashboard` | Company Admin | **master** (“Delegate a task”) |
| 3 | CEO / Executive | `/dashboard/executive` | CEO | **executive** |
| 4 | Sales | `/dashboard/sales` | Sales Manager, Sales Executive | **sales** |
| 5 | CRM | `/dashboard/crm` | Company Admin, Sales Manager, Sales Executive | **sales** |
| 6 | HR | `/dashboard/hr` | HR Manager | **hr** |
| 7 | Finance | `/dashboard/finance` | Finance Manager, Accountant | **finance** |
| 8 | Customer Support | `/dashboard/support` | Customer Support | **support** |
| 9 | Marketing | `/dashboard/marketing` | Marketing Manager | **marketing** |
| 10 | Operations | `/dashboard/operations` | Operations Manager | **inventory** |
| 11 | Employee | `/dashboard/employee` | Employee | **executive** (“Ask AI”) + per-employee chat |
| 12 | AI Employees | `/dashboard/employees` | Super Admin, Company Admin, CEO | per-AI-employee chat (`?employee=<id>`) |
| 13 | Reports & Analytics | `/dashboard/analytics` | Super Admin, Company Admin, CEO, Sales/HR/Finance/Marketing/Operations Managers | — |
| 14 | Settings & Integrations | `/dashboard/settings` | Super Admin, Company Admin, CEO | — (integration Connect buttons) |

**How the wiring works** (`frontend/src/lib/agents.ts` + `dashboards.ts`):
- Each dashboard’s “Ask AI …” button pre-binds chat via `/dashboard/chat?agent=<key>` → the backend resolves that key to the matching AI employee (e.g. `?agent=sales` → “AI Sales Assistant”).
- Opening AI Chat without an agent binds the user’s own role (`ROLE_TO_AGENT`): Sales→sales, Finance→finance, Accountant→accountant, HR→hr, Support→support, Marketing→marketing, Operations→inventory, CEO→executive, Company/Super Admin→master.
- `?employee=<id>` binds a specific AI employee (from Employee or AI Employees dashboards).
- Agent keys: sales, support, hr, recruiter, finance, accountant, marketing, content_writer, legal, inventory, procurement, executive, master.

---

## 7. Background Workers (`backend/workers/`, Celery + Redis)

| Task | Module | Schedule |
|---|---|---|
| `workers.ai_generate` | ai_worker | on-demand (batch/non-interactive agent turns) |
| `workers.send_email` | email_worker | on-demand — provider cascade Gmail → Outlook → M365 |
| `workers.send_whatsapp` | whatsapp_worker | on-demand |
| `workers.process_document` | document_worker | on-demand (upload → OCR/extract) |
| `workers.embed_document` / `workers.embed_memory` | embedding_worker | on-demand (chunk + embed, RAG) |
| `workers.generate_report` | report_worker | on-demand (heavy report/PDF) |
| `workers.deliver_notification` | notification_worker | on-demand (best-effort fan-out) |
| `workers.check_stale_customer_threads` | followup_worker | **every hour** (minute 0) |
| `workers.generate_due_recurring_invoices` | recurring_invoice_worker | **daily 01:00** |

---

## 8. Workflows

### A. Invoice-paid chain (`workflow_service.on_invoice_paid`)
Marked paid (`mark_invoice_paid`) → best-effort chain (each step isolated):
1. **Receipt** — generate + persist receipt PDF
2. **CRM** — log `Invoice X paid` activity on the customer
3. **Notify sales** — org notification + Slack post (optional)
4. **Thank-you email** — via connected Gmail (skipped gracefully if not connected)
5. **Follow-up reminder** — 30 days out (`FOLLOWUP_DAYS = 30`)

### B. Stale-customer follow-up scan (hourly)
Open deals where last contact (CRM activity or email) is older than 3 days → create a follow-up Reminder; idempotent via 24-hour dedup window.

### C. Recurring invoices (daily 01:00)
Due invoices (`next_billing_date <= today`) → clone as unpaid invoice (+ line items), advance source's `next_billing_date` by the recurrence interval (daily/weekly/monthly/yearly).

### D. Email cascade
`workers.send_email` picks the first connected provider: Gmail → Outlook → Microsoft 365; retries (max 3) on failure; no-op if none connected.

### E. Document pipeline
Upload → `process_document` (extract text/OCR) → `embed_document` (chunk + pgvector embeddings) → RAG search via `search_knowledge`.

---

## 9. Key Configuration (`backend/.env`)

**Core:** `DATABASE_URL`, `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`/`SUPABASE_JWT_SECRET`, `ENCRYPTION_KEY`, `REDIS_URL`, `FRONTEND_ORIGIN` (comma-separated; CORS), `ENVIRONMENT`.

**LLM:** `DEFAULT_AI_MODEL=gemini-3.5-flash`, `AI_MODEL_FALLBACKS=gemini-3.5-flash-lite,gemini-3.1-flash-lite`, `AI_MAX_TOKENS=1024`, optional `OPENROUTER_API_KEY`/`OPENROUTER_BASE_URL`, optional `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`/`GOOGLE_AI_KEY` (Google key is the live provider).

**OAuth:** `GMAIL_CLIENT_ID/SECRET` (+ google family redirect URIs), `MICROSOFT_CLIENT_ID/SECRET` (+ outlook/365/onedrive redirect URIs), `SLACK_*`, `ZOHO_*` (+ `ZOHO_DATA_CENTER`), `XERO_*` (+ `XERO_SCOPES=openid profile email accounting.invoices accounting.contacts accounting.settings offline_access`).

**Env-key:** `WHATSAPP_API_TOKEN/PHONE_ID/VERIFY_TOKEN`, `STRIPE_SECRET_KEY/WEBHOOK_SECRET`, `STORAGE_PROVIDER=r2`, `S3_ENDPOINT_URL`/`S3_ACCESS_KEY_ID`/`S3_SECRET_ACCESS_KEY`/`S3_BUCKET` (bucket `ai-employees-os`), `S3_REGION=auto`.

**Redirect URIs (dev):** `http://localhost:8000/api/v1/integrations/oauth/callback/{google|microsoft|slack|zoho|xero}` · Webhooks: `/api/v1/whatsapp/webhook`, `/api/v1/invoices/stripe-webhook`, `/api/v1/billing/stripe/webhook`.

---

## 10. Recent changes (2026-08-11/12) baked into this doc

- Gemini 2.5 Flash/Pro default chain + image/screenshot understanding end-to-end.
- Xero scopes corrected to granular (`accounting.invoices`) — Xero connect fixed.
- Zoho data-center support (`ZOHO_DATA_CENTER`) + offline grant for non-`com`.
- WhatsApp/Stripe/R2 Connect buttons with live connectivity checks; connected flags persist across refresh.
- Outlook/M365 `offline_access` scope fix; `save_credentials` refresh-token preservation fix.
- OAuth callback org-existence validation (no more 500 on forged state).
- Env-key status persistence (whatsapp/stripe/r2 stay Connected after refresh).
- **Google app published to production** — new orgs self-connect their own Google accounts (no test-user wall).
- **Google Calendar `timeMin` bug fixed** — client sent `timeMin: "now"` (rejected 400); now omits it or uses an RFC3339 value; live-probed OK for a fresh org.
- **Dashboards/roles/agents matrix documented** (this section 6).

## 11. Changes 2026-10-28

- **Auth:** added JWKS (ES256/RS256) verification path — fixed blanket 401 "Invalid token" / `malformed_token` against current Supabase projects.
- **LLM:** migrated off retired `gemini-2.5-flash`/`gemini-2.5-pro` to the `gemini-3.5-flash` chain (Google 404s the retired ids).
- **AI Chat agent picker:** Super Admin / Company Admin / CEO can pick any of the 13 agents for a new conversation (`canPickAllAgents`); other roles keep their fixed dashboard agent.
- **UI cleanup:** removed the placeholder Settings → API Keys tab and the non-functional "New Workflow" button (builder/executor not implemented; Workflows page is read-only).
