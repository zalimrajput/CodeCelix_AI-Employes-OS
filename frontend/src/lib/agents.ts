// Agent → AI employee mapping.
//
// The backend runs whichever agent is bound to a conversation's AI employee
// (employee.role → resolve_agent). Dashboards link to `/dashboard/chat?agent=<key>`
// so the chat pre-binds new conversations to the right specialist agent instead
// of always defaulting to the first AI employee.
import type { AIEmployee } from "@/lib/api/types";
import { ROLES, primaryRole, type UserRole } from "@/lib/roles";

/** Agent keys that a dashboard may request (`/dashboard/chat?agent=sales`). */
export const AGENT_KEYS = [
  "sales",
  "support",
  "hr",
  "recruiter",
  "finance",
  "accountant",
  "marketing",
  "content_writer",
  "legal",
  "inventory",
  "procurement",
  "executive",
  "master",
] as const;

export type AgentKey = (typeof AGENT_KEYS)[number];

/** Agent key → the AI employee role that resolves to that agent. */
export const AGENT_EMPLOYEE_ROLES: Record<AgentKey, string> = {
  sales: "Sales Assistant",
  support: "Customer Support Agent",
  hr: "HR Assistant",
  recruiter: "Recruiter",
  finance: "Finance Assistant",
  accountant: "Accountant",
  marketing: "Marketing Assistant",
  content_writer: "Content Writer",
  legal: "Legal Assistant",
  inventory: "Inventory Manager",
  procurement: "Procurement Assistant",
  executive: "Executive Assistant",
  master: "Master Coordinator",
};

/**
 * Human roles that get the full agent picker in AI Chat. Only platform and
 * company leadership can start a conversation with ANY agent; every other
 * role keeps its single fixed dashboard agent.
 */
const FULL_AGENT_ACCESS_ROLES: string[] = [
  ROLES.SUPER_ADMIN,
  ROLES.COMPANY_ADMIN,
  ROLES.CEO,
];

/** Whether the user may pick any agent in AI Chat (leadership roles only). */
export function canPickAllAgents(roles: string[] | null | undefined): boolean {
  if (!roles) return false;
  return FULL_AGENT_ACCESS_ROLES.some((r) => roles.includes(r));
}

/**
 * Human role → agent key. Used when a user opens AI Chat directly (no
 * `?agent=` from a dashboard): the chat binds to the agent of the user's own
 * department instead of always defaulting to the first AI employee.
 */
export const ROLE_TO_AGENT: Partial<Record<UserRole, AgentKey>> = {
  [ROLES.SALES_MANAGER]: "sales",
  [ROLES.SALES_EXECUTIVE]: "sales",
  [ROLES.FINANCE_MANAGER]: "finance",
  [ROLES.ACCOUNTANT]: "accountant",
  [ROLES.HR_MANAGER]: "hr",
  [ROLES.CUSTOMER_SUPPORT]: "support",
  [ROLES.MARKETING_MANAGER]: "marketing",
  [ROLES.OPERATIONS_MANAGER]: "inventory",
  [ROLES.CEO]: "executive",
  [ROLES.COMPANY_ADMIN]: "master",
  [ROLES.SUPER_ADMIN]: "master",
};

/**
 * The agent key matching a user's most relevant role (Sales Executive →
 * "sales"), or null when no role maps. Pass the user's full roles list.
 */
export function agentForRoles(roles: string[] | null | undefined): AgentKey | null {
  if (!roles) return null;
  const role = primaryRole(roles);
  if (!role) return null;
  return ROLE_TO_AGENT[role] ?? null;
}

/** The AI employee that answers for an agent key, or undefined when missing. */
export function employeeForAgent(
  employees: AIEmployee[],
  agentKey: string | null | undefined
): AIEmployee | undefined {
  if (!agentKey) return undefined;
  const role = AGENT_EMPLOYEE_ROLES[agentKey as AgentKey];
  if (!role) return undefined;
  return employees.find((e) => e.role === role);
}

/** The AI employee whose role resolves to the given agent key, by display name. */
export function agentDisplayName(agentKey: string | null | undefined): string | null {
  if (!agentKey) return null;
  const role = AGENT_EMPLOYEE_ROLES[agentKey as AgentKey];
  if (!role) return null;
  // AI employees are seeded as "AI <Role>" (e.g. "AI Sales Assistant").
  return `AI ${role}`;
}
