# AI Employee OS — Frontend Application

Next.js (App Router) single-page application and multi-tenant management interface for **AI Employee OS**. Provides role-based dashboards, interactive AI chat with live tool-calling feedback, CRM/Finance/HR modules, and third-party integration settings.

---

## Tech Stack

- **Framework:** [Next.js 16](https://nextjs.org/) (App Router)
- **UI & Styling:** [Tailwind CSS v4](https://tailwindcss.com/), Lucide Icons, Framer Motion
- **State & Data Fetching:** [@tanstack/react-query](https://tanstack.com/query/latest), React Hook Form, Zod
- **Data Visualization:** Recharts
- **Authentication & DB Client:** [@supabase/ssr](https://supabase.com/docs/guides/auth/server-side/nextjs), `@supabase/supabase-js`
- **HTTP Client:** Axios

---

## Directory Structure

```text
frontend/
├── src/
│   ├── app/               # Next.js App Router pages and route handlers
│   │   ├── (auth)/        # Sign in, signup, and authentication flows
│   │   ├── dashboard/     # Role-based dashboards (CRM, Sales, HR, Finance, AI Chat, etc.)
│   │   └── api/           # Frontend Next.js API routes / proxies
│   ├── components/        # Reusable UI widgets, layout components, and charts
│   ├── hooks/             # Custom React hooks (auth, query hooks, UI state)
│   ├── lib/               # Utility functions, API client, agent & dashboard registries
│   └── types/             # TypeScript interfaces and schema types
├── public/                # Static assets and icons
├── .env.example           # Example environment variable file
├── package.json           # Scripts and dependencies
└── tsconfig.json          # TypeScript configuration
```

---

## Getting Started

### Prerequisites

- **Node.js 20+** and **npm** (or pnpm / yarn)
- Running **FastAPI Backend** (`http://localhost:8000`)
- Running **Supabase** instance (Local or Cloud)

---

### Environment Setup

1. Copy the example environment file:
   ```bash
   cp .env.example .env.local
   ```
2. Populate `.env.local` with your credentials:
   ```env
   # Supabase client credentials
   NEXT_PUBLIC_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
   NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key

   # Backend API URL (FastAPI)
   NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
   ```

---

### Installation & Development Server

1. **Install dependencies:**
   ```bash
   npm install
   ```

2. **Start the local development server:**
   ```bash
   npm run dev
   ```
   Open [http://localhost:3000](http://localhost:3000) in your browser.

---

### Scripts

- `npm run dev` — Starts the development server with webpack (`next dev --webpack`)
- `npm run build` — Compiles and builds the production application
- `npm run start` — Starts the production Next.js server
- `npm run lint` — Runs ESLint checks

