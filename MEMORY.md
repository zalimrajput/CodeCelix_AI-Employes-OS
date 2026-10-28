# Project Memory

> 📌 **Current maintained snapshot: [SYSTEM_SETUP.md](SYSTEM_SETUP.md)** — agents, tools, integrations, workers, workflows, and configuration.

This document tracks the long-term context, architectural decisions, and technical debt of the AI Employee OS project.

## 1. Architecture Decisions
- **Source of Truth for Auth:** Supabase Auth is the absolute source of truth. We explicitly rejected local backend password hashing to prevent conflicts and ensure Row Level Security (RLS) policies work seamlessly with the Supabase JWT.
- **Source of Truth for Schema:** The Supabase SQL migrations (`supabase/migrations/`) dictate the schema. The backend SQLAlchemy models exist purely to query this schema and must be manually kept in sync. Alembic is not used to create tables.
- **Multi-Tenancy:** Enforced by Postgres RLS using the `organization_id` column. We use a custom Postgres function `current_org_id()` to extract the organization ID safely during queries.

## 2. Naming Conventions
- **Database Tables:** `snake_case`, plural (e.g., `ai_employees`, `invoices`).
- **Python Backend:**
  - Files/Modules: `snake_case.py`
  - Classes: `PascalCase`
  - Functions/Variables: `snake_case`
- **TypeScript Frontend:**
  - Files/Components: `kebab-case.tsx` or `kebab-case.ts`
  - Interfaces/Types: `PascalCase`
  - Variables/Functions: `camelCase`

## 3. Completed Work
- **Database Schema:** 64+ migrations → 71 tables across 20+ modules (CRM, HR, Sales, Billing) with full RLS multi-tenancy.
- **Backend + AI Engine:** FastAPI API with **14 AI agents** (master coordinator + 13 specialists) and **59 tools**; model router (Gemini 3.5 Flash default, lite fallbacks, OpenRouter optional) with image/screenshot understanding; RAG (pgvector, OpenAI → Gemini embedding fallback).
- **Integrations:** 13 providers (Google ×4, Microsoft ×3, Slack, Zoho, Xero, WhatsApp, Stripe, R2) — per-org encrypted OAuth tokens with auto-refresh.
- **Workers:** Celery (email cascade, WhatsApp, documents, embeddings, reports, notifications, follow-up scan, recurring invoices).
- **Frontend:** Next.js dashboards wired to the backend; auth via Supabase JWT.
- **Tests:** Backend test suite passing (agents, model-router fallback, integrations, auth, workflows).

## 4. Pending Work (production hardening)
- **Google:** publish OAuth app to production + app verification for sensitive scopes (removes warning + 100-user cap).
- **WhatsApp:** real business number + Meta business verification (currently a test number).
- **Xero:** App Store certification so other organisations can connect.
- **Slack:** public distribution for other workspaces.
- **Infra:** own domain + HTTPS deployment (redirect URIs currently localhost/ngrok).

## 5. Known Issues & Technical Debt *(historical — resolved during implementation)*
- **Corrupted Virtual Environment:** The `backend/venv` currently contains only `pip` and `setuptools`. Dependencies are not installed.
- **Dependency Conflicts:** `requirements.txt` includes `pyjwt` instead of `python-jose`, missing `email-validator`, and uses the async postgres driver incorrectly for sync SQLAlchemy setup.
- **Model Drift:** The existing backend models (e.g., `User`) do not match the updated Supabase schema (e.g., expecting `password_hash` which was dropped in migration 0057).
- **Security Flaw in `database.py`:** The database connection string is printed to `stdout`, risking credential leakage.

## 6. Important Assumptions
- Super Admins will bypass RLS to manage the platform.
- Organizations are completely siloed; no data sharing occurs between organizations.
- Background jobs (Celery) will handle long-running tasks like document embedding and bulk email processing to keep API response times low.

## 7. Future Considerations
- Transitioning to edge functions for simple CRUD operations to reduce FastAPI load.
- Implementing WebSocket infrastructure for real-time AI typing indicators and notification delivery.
