// Central dashboard registry for AI Employee OS.
// Mirrors supabase/migrations/0060_platform_roles_and_seeds.sql section 4:
// the 14 dashboards seeded into `dashboards` + `dashboard_role_access`.
// Every dashboard lists the roles that may see it (role access mirror).
import {
  BarChart3,
  Bot,
  Briefcase,
  Crown,
  Headset,
  LayoutDashboard,
  Megaphone,
  Settings,
  ShieldCheck,
  TrendingUp,
  UserCog,
  Users,
  Wallet,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { ROLES, type UserRole } from "./roles";
import { dashboardsForModules } from "./modules";

export type DashboardGroup =
  | "platform"
  | "company"
  | "department"
  | "personal"
  | "system";

export interface DashboardDef {
  id: string;
  /** Matches the seeded `dashboards.name` value. */
  name: string;
  description: string;
  href: string;
  icon: LucideIcon;
  /** Mirrors the seeded `dashboard_role_access.role_name` rows. */
  roles: UserRole[];
  group: DashboardGroup;
  /** Gradient used for the icon tile. */
  gradient: string;
}

/** Legacy names (migration 0059) normalized to their current equivalents.
 *  Legacy "Employee" is intentionally left as-is: the Employee/User role it
 *  used to point to was removed, so old staff keep the personal dashboard. */
const LEGACY_MAP: Record<string, UserRole> = {
  [ROLES.LEGACY_OWNER]: ROLES.COMPANY_ADMIN,
  [ROLES.LEGACY_ADMIN]: ROLES.COMPANY_ADMIN,
};

function normalize(roles: string[] | undefined | null): UserRole[] {
  const out: UserRole[] = [];
  for (const r of roles ?? []) {
    const mapped = (LEGACY_MAP[r] ?? r) as UserRole;
    if (!out.includes(mapped)) out.push(mapped);
  }
  return out;
}

export const DASHBOARDS: DashboardDef[] = [
  {
    id: "super-admin",
    name: "Super Admin Dashboard",
    description: "Platform-wide administration and company oversight.",
    href: "/dashboard/super-admin",
    icon: ShieldCheck,
    roles: [ROLES.SUPER_ADMIN],
    group: "platform",
    gradient: "from-danger to-warning",
  },
  {
    id: "company-admin",
    name: "Company Admin Dashboard",
    description: "Company-wide overview and member management.",
    href: "/dashboard",
    icon: LayoutDashboard,
    roles: [ROLES.COMPANY_ADMIN],
    group: "company",
    gradient: "from-primary to-secondary",
  },
  {
    id: "executive",
    name: "CEO / Executive Dashboard",
    description: "Executive KPIs, revenue, and high-level analytics.",
    href: "/dashboard/executive",
    icon: Crown,
    roles: [ROLES.CEO],
    group: "company",
    gradient: "from-accent to-primary",
  },
  {
    id: "sales",
    name: "Sales Dashboard",
    description: "Sales pipeline, leads, and quotation performance.",
    href: "/dashboard/sales",
    icon: TrendingUp,
    roles: [ROLES.SALES_MANAGER, ROLES.SALES_EXECUTIVE],
    group: "department",
    gradient: "from-success to-accent",
  },
  {
    id: "crm",
    name: "CRM Dashboard",
    description: "Customers, leads, and relationship insights.",
    href: "/dashboard/crm",
    icon: Users,
    roles: [ROLES.COMPANY_ADMIN, ROLES.SALES_MANAGER, ROLES.SALES_EXECUTIVE],
    group: "department",
    gradient: "from-primary to-accent",
  },
  {
    id: "hr",
    name: "HR Dashboard",
    description: "Employees, attendance, and hiring overview.",
    href: "/dashboard/hr",
    icon: UserCog,
    roles: [ROLES.HR_MANAGER],
    group: "department",
    gradient: "from-warning to-danger",
  },
  {
    id: "finance",
    name: "Finance Dashboard",
    description: "Revenue, expenses, budgets, and cash flow.",
    href: "/dashboard/finance",
    icon: Wallet,
    roles: [ROLES.FINANCE_MANAGER, ROLES.ACCOUNTANT],
    group: "department",
    gradient: "from-success to-primary",
  },
  {
    id: "support",
    name: "Customer Support Dashboard",
    description: "Support tickets, email, and WhatsApp activity.",
    href: "/dashboard/support",
    icon: Headset,
    roles: [ROLES.CUSTOMER_SUPPORT],
    group: "department",
    gradient: "from-accent to-success",
  },
  {
    id: "marketing",
    name: "Marketing Dashboard",
    description: "Campaigns, content, and audience performance.",
    href: "/dashboard/marketing",
    icon: Megaphone,
    roles: [ROLES.MARKETING_MANAGER],
    group: "department",
    gradient: "from-secondary to-danger",
  },
  {
    id: "operations",
    name: "Operations Dashboard",
    description: "Tasks, workflows, and operational efficiency.",
    href: "/dashboard/operations",
    icon: Workflow,
    roles: [ROLES.OPERATIONS_MANAGER],
    group: "department",
    gradient: "from-warning to-accent",
  },
  {
    id: "employee",
    name: "Employee Dashboard",
    description: "Personal tasks, deadlines, and AI assistant access.",
    href: "/dashboard/employee",
    icon: Briefcase,
    // Legacy migration-0059 "Employee" role only — the assignable
    // "Employee/User" role it used to share this page with was removed.
    roles: [ROLES.LEGACY_EMPLOYEE],
    group: "personal",
    gradient: "from-primary to-success",
  },
  {
    id: "ai-employees",
    name: "AI Employees Dashboard",
    description: "Manage the AI workforce, tools, and usage.",
    href: "/dashboard/employees",
    icon: Bot,
    // Super Admin included so the platform admin can open the AI workforce
    // page from the main nav (their data views render cross-tenant).
    roles: [ROLES.SUPER_ADMIN, ROLES.COMPANY_ADMIN, ROLES.CEO],
    group: "system",
    gradient: "from-secondary to-accent",
  },
  {
    id: "reports",
    name: "Reports & Analytics Dashboard",
    description: "Reports and analytics for managers and above.",
    href: "/dashboard/analytics",
    icon: BarChart3,
    // Super Admin included so the platform admin can open Analytics from the
    // main nav (their data views render cross-tenant).
    roles: [
      ROLES.SUPER_ADMIN,
      ROLES.COMPANY_ADMIN,
      ROLES.CEO,
      ROLES.SALES_MANAGER,
      ROLES.HR_MANAGER,
      ROLES.FINANCE_MANAGER,
      ROLES.MARKETING_MANAGER,
      ROLES.OPERATIONS_MANAGER,
    ],
    group: "system",
    gradient: "from-accent to-secondary",
  },
  {
    id: "settings",
    name: "Settings & Integrations Dashboard",
    description: "Company settings and connected applications.",
    href: "/dashboard/settings",
    icon: Settings,
    // Super Admin included so the platform admin can open Settings too — the
    // page degrades gracefully for org-less accounts (empty lists + defaults).
    roles: [ROLES.SUPER_ADMIN, ROLES.COMPANY_ADMIN, ROLES.CEO],
    group: "system",
    gradient: "from-slate-500 to-slate-400",
  },
];

/**
 * Dashboards a user may access, based on their role names.
 * Company Admin (and legacy Owner/Admin) has FULL access to every dashboard
 * within their own company — only the platform-level Super Admin dashboard
 * stays exclusive to the Super Admin role. The CEO sees the full company set
 * too, while department roles see exactly their own dashboards.
 */
export function dashboardsForRoles(
  roles: string[] | undefined | null
): DashboardDef[] {
  const normalized = normalize(roles);
  // Super Admin oversees the whole platform: every dashboard is open to
  // them (the org preview system gives cross-tenant views on the data).
  if (normalized.includes(ROLES.SUPER_ADMIN)) {
    return DASHBOARDS;
  }
  // normalize() already maps legacy Owner/Admin -> Company Admin.
  const fullCompany =
    normalized.includes(ROLES.COMPANY_ADMIN) ||
    normalized.includes(ROLES.CEO);
  if (fullCompany) {
    return DASHBOARDS.filter((d) => d.id !== "super-admin");
  }
  return DASHBOARDS.filter((d) =>
    d.roles.some((r) => normalized.includes(r))
  );
}

/**
 * A redirect target that passes BOTH the role check and the module gate.
 * Used by the layout guard so a user whose home dashboard's module was
 * disabled (org admin / super admin) never loops redirects into itself.
 * Falls back to the main dashboard (module "overview", never guarded).
 */
export function safeHomePathForRoles(
  roles: string[] | undefined | null,
  enabledModules: string[] | undefined | null
): string {
  const accessible = dashboardsForModules(
    dashboardsForRoles(roles),
    enabledModules
  );
  if (accessible.length > 0) return accessible[0].href;
  return "/dashboard";
}


