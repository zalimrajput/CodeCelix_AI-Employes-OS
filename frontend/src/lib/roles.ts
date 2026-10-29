// Centralized human-role definitions for AI Employee OS.
// Mirrors supabase/migrations/0059_seed_default_roles.sql (legacy 3-role seed)
// and 0060_platform_roles_and_seeds.sql (full 12-role model):
//   1 platform role: Super Admin
//   10 company roles: Company Admin, CEO / Executive, Sales Manager, Sales
//   Executive, HR Manager, Finance Manager, Accountant, Customer Support,
//   Marketing Manager, Operations Manager.
// (The former "Employee/User" role was removed — legacy \"Employee\" rows from
// 0059 orgs keep their access below.)

export const ROLES = {
  SUPER_ADMIN: "Super Admin",

  COMPANY_ADMIN: "Company Admin",
  CEO: "CEO / Executive",
  SALES_MANAGER: "Sales Manager",
  SALES_EXECUTIVE: "Sales Executive",
  HR_MANAGER: "HR Manager",
  FINANCE_MANAGER: "Finance Manager",
  ACCOUNTANT: "Accountant",
  CUSTOMER_SUPPORT: "Customer Support",
  MARKETING_MANAGER: "Marketing Manager",
  OPERATIONS_MANAGER: "Operations Manager",

  // Legacy names from migration 0059 (existing orgs keep these rows).
  LEGACY_OWNER: "Owner",
  LEGACY_ADMIN: "Admin",
  LEGACY_EMPLOYEE: "Employee",
} as const;

export type UserRole = (typeof ROLES)[keyof typeof ROLES];

export interface RoleMeta {
  label: string;
  badgeClass: string;
  description: string;
}

export const ROLE_META: Record<string, RoleMeta> = {
  [ROLES.SUPER_ADMIN]: {
    label: "Super Admin",
    badgeClass:
      "bg-danger/15 border border-danger/40 text-danger",
    description: "Platform-wide administration",
  },
  [ROLES.COMPANY_ADMIN]: {
    label: "Company Admin",
    badgeClass:
      "bg-gradient-to-r from-primary/25 to-secondary/25 border border-primary/40 text-primary-soft",
    description: "Full control over the workspace",
  },
  [ROLES.CEO]: {
    label: "CEO",
    badgeClass: "bg-accent/15 border border-accent/40 text-accent",
    description: "Oversees the whole company",
  },
  [ROLES.SALES_MANAGER]: {
    label: "Sales Manager",
    badgeClass: "bg-primary/15 border border-primary/40 text-primary-soft",
    description: "Manages the sales team and CRM",
  },
  [ROLES.SALES_EXECUTIVE]: {
    label: "Sales Executive",
    badgeClass: "bg-slate-500/15 border border-slate-500/40 text-slate-300",
    description: "Works leads, deals, and quotations",
  },
  [ROLES.HR_MANAGER]: {
    label: "HR Manager",
    badgeClass: "bg-primary/15 border border-primary/40 text-primary-soft",
    description: "Manages employees and hiring",
  },
  [ROLES.FINANCE_MANAGER]: {
    label: "Finance Manager",
    badgeClass: "bg-primary/15 border border-primary/40 text-primary-soft",
    description: "Manages budgets and expenses",
  },
  [ROLES.ACCOUNTANT]: {
    label: "Accountant",
    badgeClass: "bg-slate-500/15 border border-slate-500/40 text-slate-300",
    description: "Creates invoices and records payments",
  },
  [ROLES.CUSTOMER_SUPPORT]: {
    label: "Support",
    badgeClass: "bg-slate-500/15 border border-slate-500/40 text-slate-300",
    description: "Responds to customers",
  },
  [ROLES.MARKETING_MANAGER]: {
    label: "Marketing Manager",
    badgeClass: "bg-primary/15 border border-primary/40 text-primary-soft",
    description: "Manages campaigns and content",
  },
  [ROLES.OPERATIONS_MANAGER]: {
    label: "Operations",
    badgeClass: "bg-primary/15 border border-primary/40 text-primary-soft",
    description: "Manages tasks and workflows",
  },
  [ROLES.LEGACY_OWNER]: {
    label: "Owner",
    badgeClass:
      "bg-gradient-to-r from-primary/25 to-secondary/25 border border-primary/40 text-primary-soft",
    description: "Full control over the workspace",
  },
  [ROLES.LEGACY_ADMIN]: {
    label: "Admin",
    badgeClass: "bg-accent/15 border border-accent/40 text-accent",
    description: "Manages the AI workforce",
  },
  [ROLES.LEGACY_EMPLOYEE]: {
    label: "Employee",
    badgeClass: "bg-slate-500/15 border border-slate-500/40 text-slate-300",
    description: "Uses assigned tools",
  },
};

const ROLE_PRIORITY: Record<string, number> = {
  [ROLES.SUPER_ADMIN]: 20,
  [ROLES.COMPANY_ADMIN]: 19,
  [ROLES.CEO]: 18,
  [ROLES.SALES_MANAGER]: 15,
  [ROLES.HR_MANAGER]: 15,
  [ROLES.FINANCE_MANAGER]: 15,
  [ROLES.MARKETING_MANAGER]: 15,
  [ROLES.OPERATIONS_MANAGER]: 15,
  [ROLES.SALES_EXECUTIVE]: 12,
  [ROLES.ACCOUNTANT]: 11,
  [ROLES.CUSTOMER_SUPPORT]: 10,
  [ROLES.LEGACY_OWNER]: 19,
  [ROLES.LEGACY_ADMIN]: 16,
  [ROLES.LEGACY_EMPLOYEE]: 9,
};

// Roles that manage something (managers and above) — treated as admin-level.
const ADMIN_MIN_PRIORITY = 14;

/** The user's most privileged role, or null when they have no roles yet. */
export function primaryRole(roles: string[] | undefined | null): UserRole | null {
  if (!roles || roles.length === 0) return null;
  const known = roles.filter((r): r is UserRole => r in ROLE_PRIORITY);
  if (known.length === 0) return null;
  return known.sort((a, b) => ROLE_PRIORITY[b] - ROLE_PRIORITY[a])[0];
}

/** Whether a role may see admin-level navigation and settings. */
export function isAdmin(roles: string[] | undefined | null): boolean {
  const role = primaryRole(roles);
  if (!role) return false;
  return ROLE_PRIORITY[role] >= ADMIN_MIN_PRIORITY;
}

/** Routes reserved for admins; staff are redirected away. */
export const ADMIN_ONLY_PATHS = [
  "/dashboard/employees",
  "/dashboard/workflows",
  "/dashboard/analytics",
  "/dashboard/billing",
  "/dashboard/settings",
];

/** The primary dashboard a role should land on after login. */
const HOME_BY_ROLE: Record<string, string> = {
  [ROLES.SUPER_ADMIN]: "/dashboard/super-admin",
  [ROLES.COMPANY_ADMIN]: "/dashboard",
  [ROLES.CEO]: "/dashboard/executive",
  [ROLES.SALES_MANAGER]: "/dashboard/sales",
  [ROLES.SALES_EXECUTIVE]: "/dashboard/sales",
  [ROLES.HR_MANAGER]: "/dashboard/hr",
  [ROLES.FINANCE_MANAGER]: "/dashboard/finance",
  [ROLES.ACCOUNTANT]: "/dashboard/finance",
  [ROLES.CUSTOMER_SUPPORT]: "/dashboard/support",
  [ROLES.MARKETING_MANAGER]: "/dashboard/marketing",
  [ROLES.OPERATIONS_MANAGER]: "/dashboard/operations",
  [ROLES.LEGACY_OWNER]: "/dashboard",
  [ROLES.LEGACY_ADMIN]: "/dashboard",
  [ROLES.LEGACY_EMPLOYEE]: "/dashboard/employee",
};

/** Where a signed-in user should land based on their role. */
export function homePathForRoles(roles: string[] | undefined | null): string {
  const role = primaryRole(roles);
  if (!role) return "/dashboard/tasks";
  return HOME_BY_ROLE[role] ?? "/dashboard";
}
