# Dashboard Matrix — Agents & Human Roles

**Snapshot date:** 2026-10-28 · **Source of truth:** `frontend/src/lib/dashboards.ts`, `frontend/src/lib/agents.ts`, `frontend/src/lib/roles.ts`, and the dashboard pages under `frontend/src/app/(app)/dashboard/**`.

This document answers two questions:
1. **Which AI agent works with which dashboard?**
2. **Which human role can access which dashboards?**

The dashboard registry, role-access matrix and agent wiring are all enforced in code — this document mirrors them exactly.

---

## 1. The 14 dashboards at a glance

| # | Dashboard | Route | Group |
|---|---|---|---|
| 1 | Super Admin | `/dashboard/super-admin` | Platform |
| 2 | Company Admin | `/dashboard` | Company |
| 3 | CEO / Executive | `/dashboard/executive` | Company |
| 4 | Sales | `/dashboard/sales` | Department |
| 5 | CRM | `/dashboard/crm` | Department |
| 6 | HR | `/dashboard/hr` | Department |
| 7 | Finance | `/dashboard/finance` | Department |
| 8 | Customer Support | `/dashboard/support` | Department |
| 9 | Marketing | `/dashboard/marketing` | Department |
| 10 | Operations | `/dashboard/operations` | Department |
| 11 | Employee | `/dashboard/employee` | Personal |
| 12 | AI Employees | `/dashboard/employees` | System |
| 13 | Reports & Analytics | `/dashboard/analytics` | System |
| 14 | Settings & Integrations | `/dashboard/settings` | System |

---

## 2. Which AI agent works with which dashboard

Each dashboard's **"Ask AI …" button** pre-binds a new chat to a specialist agent via `/dashboard/chat?agent=<key>`. The AI Employees dashboard instead binds chats to **specific AI employees** (`?employee=<id>`).

| Dashboard | Linked AI agent | Agent key | How the link works |
|---|---|---|---|
| Super Admin | AI Manager | `master` | delegates via master |
| Company Admin | AI Manager | `master` | “Delegate a task” button (`?agent=master`) |
| CEO / Executive | Executive Assistant | `executive` | “Ask AI Executive” (`?agent=executive`) |
| Sales | Sales Agent | `sales` | “Delegate follow-ups” (`?agent=sales`) |
| CRM | Sales Agent | `sales` | “Ask AI Sales” (`?agent=sales`) |
| HR | HR Assistant | `hr` | “Ask AI HR” (`?agent=hr`) |
| Finance | Finance Manager | `finance` | “Ask AI Finance” (`?agent=finance`) |
| Customer Support | Customer Support | `support` | “Ask AI Support” (`?agent=support`) |
| Marketing | Marketing Manager | `marketing` | “Ask AI Marketing” (`?agent=marketing`) |
| Operations | Inventory Manager | `inventory` | “Ask AI Operations” (`?agent=inventory`) |
| Employee | Executive Assistant | `executive` | “Ask AI” (`?agent=executive`) + per-employee chat |
| AI Employees | **Any of the 13 AI employees** | `?employee=<id>` | per-employee chat button on each employee card/profile |
| Reports & Analytics | — | — | no direct agent button |
| Settings & Integrations | — | — | no direct agent button |

### Reverse view — which dashboards surface each agent

| Agent key | AI employee | Surfaced on dashboards |
|---|---|---|
| `sales` | AI Sales Assistant | Sales, CRM |
| `support` | AI Customer Support Agent | Customer Support |
| `hr` | AI HR Assistant | HR |
| `recruiter` | AI Recruiter | AI Employees (per-employee chat only) |
| `finance` | AI Finance Assistant | Finance |
| `accountant` | AI Accountant | AI Employees (per-employee chat) · bound by Accountant role |
| `marketing` | AI Marketing Assistant | Marketing |
| `content_writer` | AI Content Writer | AI Employees (per-employee chat only) |
| `legal` | AI Legal Assistant | AI Employees (per-employee chat only) |
| `inventory` | AI Inventory Manager | Operations |
| `procurement` | AI Procurement Assistant | AI Employees (per-employee chat only) |
| `executive` | AI Executive Assistant | CEO / Executive, Employee |
| `master` | AI Manager (Master Coordinator) | Company Admin, Super Admin |

### Chat without a dashboard link
When a user opens **AI Chat directly** (no `?agent=`), the chat binds to the agent of the user's own role (see `ROLE_TO_AGENT` in section 3).

### Agent picker (leadership only)
**Super Admin, Company Admin and CEO** additionally get an **agent picker** in AI Chat (`canPickAllAgents` in `frontend/src/lib/agents.ts`): when starting a new conversation they may choose **any of the 13 agents**, overriding both the role default and any `?agent=` deep link. Every other role is fixed to its single dashboard agent — no picker is shown for them.

---

## 3. Which human role can access which dashboards

Role access is enforced twice: in the sidebar nav (role-filtered) and in the layout guard (redirects away from pages the role may not open).

| Human role | Home dashboard (after login) | Dashboards they can open |
|---|---|---|
| **Super Admin** (platform) | Super Admin | **All 14** (incl. Super Admin — exclusive to this role) |
| **Company Admin** | Company Admin | **All 13 company dashboards** (everything except Super Admin) |
| **CEO / Executive** | CEO / Executive | **All 13 company dashboards** (everything except Super Admin) |
| **Sales Manager** | Sales | Sales, CRM, Reports & Analytics |
| **Sales Executive** | Sales | Sales, CRM |
| **HR Manager** | HR | HR, Reports & Analytics |
| **Finance Manager** | Finance | Finance, Reports & Analytics |
| **Accountant** | Finance | Finance |
| **Customer Support** | Customer Support | Customer Support |
| **Marketing Manager** | Marketing | Marketing, Reports & Analytics |
| **Operations Manager** | Operations | Operations, Reports & Analytics |
| **Employee / User** | Employee | Employee |

Legacy roles (`Owner` / `Admin` / `Employee` from migration 0059) behave as **Company Admin** / **Company Admin** / **Employee**.

### Access rules in one sentence
- **Super Admin** → everything (14).
- **Company Admin & CEO** → every company dashboard (13) — the platform Super Admin dashboard stays exclusive to Super Admin.
- **Department roles** → exactly their own department dashboard(s) + Reports & Analytics where the role is a manager.
- **Employee** → only the personal Employee dashboard.

### Plus: default AI agent per role (chat opened without a dashboard link)

| Human role | Default AI agent |
|---|---|
| Super Admin | `master` |
| Company Admin | `master` |
| CEO / Executive | `executive` |
| Sales Manager / Sales Executive | `sales` |
| HR Manager | `hr` |
| Finance Manager | `finance` |
| Accountant | `accountant` |
| Customer Support | `support` |
| Marketing Manager | `marketing` |
| Operations Manager | `inventory` |
| Employee / User | per-AI-employee binding |

---

## 4. Full access matrix (dashboard × role)

| Dashboard | Super Admin | Company Admin | CEO | Sales Mgr | Sales Exec | HR Mgr | Finance Mgr | Accountant | Support | Marketing Mgr | Ops Mgr | Employee |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Super Admin | ✅ | — | — | — | — | — | — | — | — | — | — | — |
| Company Admin | ✅ | ✅ | ✅ | — | — | — | — | — | — | — | — | — |
| CEO / Executive | ✅ | ✅ | ✅ | — | — | — | — | — | — | — | — | — |
| Sales | ✅ | ✅ | ✅ | ✅ | ✅ | — | — | — | — | — | — | — |
| CRM | ✅ | ✅ | ✅ | ✅ | ✅ | — | — | — | — | — | — | — |
| HR | ✅ | ✅ | ✅ | — | — | ✅ | — | — | — | — | — | — |
| Finance | ✅ | ✅ | ✅ | — | — | — | ✅ | ✅ | — | — | — | — |
| Customer Support | ✅ | ✅ | ✅ | — | — | — | — | — | ✅ | — | — | — |
| Marketing | ✅ | ✅ | ✅ | — | — | — | — | — | — | ✅ | — | — |
| Operations | ✅ | ✅ | ✅ | — | — | — | — | — | — | — | ✅ | — |
| Employee | ✅ | ✅ | ✅ | — | — | — | — | — | — | — | — | ✅ |
| AI Employees | ✅ | ✅ | ✅ | — | — | — | — | — | — | — | — | — |
| Reports & Analytics | ✅ | ✅ | ✅ | ✅ | — | ✅ | ✅ | — | — | ✅ | ✅ | — |
| Settings & Integrations | ✅ | ✅ | ✅ | — | — | — | — | — | — | — | — | — |

**Note:** the matrix shows the strict per-role access list. In practice Company Admin and CEO (and Super Admin) open everything in their company; the department rows are what *only* those roles get beyond the admin set.

---

## 5. Code locations (enforcement)

| Concern | File |
|---|---|
| Dashboard registry + role access | `frontend/src/lib/dashboards.ts` (mirrors `supabase/migrations/0060_platform_roles_and_seeds.sql`) |
| Human roles + home paths + admin gating | `frontend/src/lib/roles.ts` |
| Agent keys, `AGENT_EMPLOYEE_ROLES`, `ROLE_TO_AGENT` | `frontend/src/lib/agents.ts` |
| Leadership agent picker gate (`canPickAllAgents`) | `frontend/src/lib/agents.ts` + `frontend/src/app/(app)/dashboard/chat/page.tsx` |
| Sidebar nav filtering | `frontend/src/components/layout/sidebar.tsx` |
| Layout role guard / redirects | `frontend/src/app/(app)/layout.tsx` |
| Backend agent resolution (role → agent) | `backend/app/ai/agents/__init__.py` (`resolve_agent`) |
