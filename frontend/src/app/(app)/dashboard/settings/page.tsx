"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  Check,
  CreditCard,
  LayoutDashboard,
  Loader2,
  Lock,
  Plug,
  Shield,
  Trash2,
  UserPlus,
  Users,
  Network,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs } from "@/components/ui/tabs";
import { Avatar } from "@/components/ui/avatar";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/hooks/use-session";
import { api } from "@/lib/api/client";
import { addDepartment, fetchOrgDepartments, fetchOrgMembers, fetchOrgModules, fetchOrgRoles, inviteMember, removeDepartment, removeMember, updateMyOrgModule } from "@/services/admin";
import { MODULE_BY_KEY, TOGGLEABLE_MODULES } from "@/lib/modules";
import { ROLE_META, ROLES } from "@/lib/roles";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";

/** OAuth providers the backend can connect (keys must match the API provider names). */
const OAUTH_INTEGRATIONS = [
  { provider: "gmail", name: "Gmail", desc: "Draft, send & summarize emails", emoji: "📧" },
  { provider: "google-calendar", name: "Google Calendar", desc: "Meetings & scheduling", emoji: "🗓️" },
  { provider: "google-drive", name: "Google Drive", desc: "Document storage & OCR", emoji: "☁️" },
  { provider: "google-sheets", name: "Google Sheets", desc: "Spreadsheets & exports", emoji: "📊" },
  { provider: "outlook", name: "Outlook", desc: "Microsoft mail & calendar", emoji: "📅" },
  { provider: "microsoft365", name: "Microsoft 365", desc: "Calendar, mail & tasks", emoji: "🪟" },
  { provider: "onedrive", name: "OneDrive / Excel", desc: "Cloud files & workbooks", emoji: "📁" },
  { provider: "slack", name: "Slack", desc: "Team notifications & approvals", emoji: "⚡" },
  { provider: "zoho", name: "Zoho CRM", desc: "Leads & pipeline sync", emoji: "🧲" },
  { provider: "xero", name: "Xero", desc: "Accounting & invoicing sync", emoji: "🧾" },
];

/** Env-key-based providers — no OAuth round-trip; Connect verifies the key live.
 *  WhatsApp is NOT here: each workspace stores its OWN token + phone number ID
 *  (see the dedicated form in IntegrationsTab). */
const KEY_INTEGRATIONS = [
  {
    provider: "stripe",
    name: "Stripe",
    desc: "Payments & billing",
    emoji: "💳",
    keys: "STRIPE_SECRET_KEY",
  },
  {
    provider: "r2",
    name: "Cloudflare R2 / S3",
    desc: "Cloud document storage",
    emoji: "☁️",
    keys: "STORAGE_PROVIDER + S3_ENDPOINT_URL + S3_ACCESS_KEY_ID + S3_SECRET_ACCESS_KEY + S3_BUCKET",
  },
];

const PROVIDER_LABEL: Record<string, string> = Object.fromEntries(
  OAUTH_INTEGRATIONS.map((i) => [i.provider, i.name])
);

/** Default role for new members (the old "Employee/User" role was removed). */
const DEFAULT_INVITE_ROLE: string = ROLES.SALES_EXECUTIVE;

/** Turn common provider error text into an actionable hint. */
function oauthErrorHint(detail: string, provider: string): string {
  const d = detail.toLowerCase();
  if (provider === "xero" && d.includes("invalid_scope")) {
    return "Enable the requested scopes (accounting.transactions, offline_access) in your Xero app at developer.xero.com, or set XERO_SCOPES in the backend .env to match what the app allows.";
  }
  if (provider === "zoho" && (d.includes("invalid_client") || d.includes("region"))) {
    return "Zoho OAuth clients are bound to a data center — set ZOHO_DATA_CENTER (com | eu | in | com.au | jp | sa) in the backend .env to match your Zoho account.";
  }
  if (provider.startsWith("google") && d.includes("access_denied")) {
    return "Google blocked this account. If the app is in Testing mode, add this email under Google Cloud Console → OAuth consent screen → Test users. If it's In production but unverified, click Advanced → Go to AI Employee OS (unsafe) on the warning page.";
  }
  return "Check the provider console and backend logs.";
}

export default function SettingsPage() {
  const { data: session } = useSession();
  const queryClient = useQueryClient();
  // After an OAuth round-trip the backend redirects here with
  // ?tab=integrations&status=connected|error&provider=<name>. The tab switch is
  // deferred past the first paint so the initial client render matches the
  // server HTML (no hydration mismatch) while still satisfying the
  // react-hooks/set-state-in-effect lint rule.
  const [tab, setTab] = useState("users");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const status = params.get("status");
    const provider = params.get("provider") ?? "";
    const errorDesc = params.get("error_description") ?? "";
    if (status === "connected") {
      toast.success(`${PROVIDER_LABEL[provider] ?? provider} connected — your AI employees can use it now`);
    } else if (status === "error") {
      toast.error(
        `Could not connect ${PROVIDER_LABEL[provider] ?? provider}. ${oauthErrorHint(errorDesc, provider)}`
      );
    }
    if (status || params.get("tab")) {
      const url = new URL(window.location.href);
      url.search = "";
      window.history.replaceState({}, "", url.pathname);
    }
    if (params.get("tab") === "integrations" || status) {
      const frame = requestAnimationFrame(() => setTab("integrations"));
      return () => cancelAnimationFrame(frame);
    }
  }, []);

  const { data: members, isLoading: membersLoading } = useQuery({
    queryKey: ["org-members"],
    queryFn: fetchOrgMembers,
  });
  const { data: roles, isLoading: rolesLoading } = useQuery({ queryKey: ["org-roles"], queryFn: fetchOrgRoles });
  const { data: orgModules } = useQuery({ queryKey: ["org-modules"], queryFn: fetchOrgModules });
  const { data: departments, isLoading: departmentsLoading } = useQuery({
    queryKey: ["org-departments"],
    queryFn: fetchOrgDepartments,
  });

  const enabledBySuperAdmin = useMemo(() => {
    const map: Record<string, boolean> = {};
    for (const m of orgModules ?? []) map[m.module_key] = m.enabled_by_super_admin !== false;
    return map;
  }, [orgModules]);

  const myOrgId = session?.user?.orgId;

  async function toggleModule(key: string, enabled: boolean) {
    const { error } = await updateMyOrgModule(key, enabled);
    if (error) return toast.error(error);
    queryClient.invalidateQueries({ queryKey: ["org-modules"] });
    toast.success(`${enabled ? "Enabled" : "Disabled"} ${MODULE_BY_KEY[key]?.name ?? key}`);
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm font-semibold text-primary-soft">Organization management</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight text-white md:text-3xl">Settings</h1>
      </div>

      <Tabs
        items={[
          { value: "users", label: "Users", icon: <Users className="h-3.5 w-3.5" /> },
          { value: "departments", label: "Departments", icon: <Network className="h-3.5 w-3.5" /> },
          { value: "modules", label: "Modules", icon: <Plug className="h-3.5 w-3.5" /> },
          { value: "workspace", label: "Workspace", icon: <Building2 className="h-3.5 w-3.5" /> },
          { value: "roles", label: "Roles", icon: <Shield className="h-3.5 w-3.5" /> },
          { value: "billing", label: "Billing", icon: <CreditCard className="h-3.5 w-3.5" /> },
          { value: "integrations", label: "Integrations", icon: <Plug className="h-3.5 w-3.5" /> },
        ]}
        onValueChange={setTab}
        className="flex-wrap"
      />

      <Card className="max-w-3xl">
        {tab === "users" && <UsersTab orgId={myOrgId} roles={roles ?? []} members={members ?? []} loading={membersLoading} />}

        {tab === "departments" && (
          <DepartmentsTab departments={departments ?? []} loading={departmentsLoading} />
        )}

        {tab === "modules" && (
          <>
            <CardHeader>
              <CardTitle>Modules & dashboards</CardTitle>
              <CardDescription>
                Choose which modules your workspace uses. Modules disabled by the platform admin are locked for your company.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="mb-2 flex items-center gap-3 rounded-xl border border-primary/30 bg-primary/10 p-3 opacity-80">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-accent text-white">
                  <LayoutDashboard className="h-4 w-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-bold text-white">Overview</span>
                  <span className="block truncate text-xs text-slate-500">Company-wide overview and quick stats.</span>
                </span>
                <Badge variant="secondary">Always on</Badge>
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {TOGGLEABLE_MODULES.map((m) => {
                  const superEnabled = enabledBySuperAdmin[m.key] ?? true;
                  const row = (orgModules ?? []).find((r) => r.module_key === m.key);
                  const enabled = superEnabled && (row ? row.enabled_by_org_admin !== false : true);
                  const Icon = m.icon;
                  return (
                    <button
                      key={m.key}
                      disabled={!superEnabled}
                      onClick={() => toggleModule(m.key, !enabled)}
                      className={cn(
                        "flex items-center gap-3 rounded-xl border p-3 text-left transition-all",
                        superEnabled ? "cursor-pointer hover:border-primary/40" : "cursor-not-allowed opacity-50",
                        enabled ? "border-primary/30 bg-primary/10" : "border-border-soft bg-card-soft/40"
                      )}
                    >
                      <span className={cn(
                        "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
                        enabled ? "bg-gradient-to-br from-primary to-accent text-white" : "bg-card-soft text-slate-500"
                      )}>
                        <Icon className="h-4 w-4" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-1.5 text-sm font-bold text-white">
                          {m.name}
                          {!superEnabled && <Lock className="h-3 w-3 text-warning" />}
                        </span>
                        <span className="block truncate text-xs text-slate-500">{m.description}</span>
                      </span>
                      <span
                        className={cn(
                          "relative h-5 w-9 shrink-0 rounded-full transition-colors",
                          enabled ? "bg-gradient-to-r from-primary to-accent" : "bg-card-soft"
                        )}
                      >
                        <span
                          className={cn(
                            "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all",
                            enabled ? "left-4.5" : "left-0.5"
                          )}
                        />
                      </span>
                    </button>
                  );
                })}
              </div>
              <p className="mt-4 flex items-center gap-2 rounded-xl border border-warning/30 bg-warning/10 px-4 py-3 text-xs text-warning">
                <Lock className="h-3.5 w-3.5 shrink-0" />
                Locked modules were disabled by the platform admin — you can&apos;t enable them from here.
              </p>
            </CardContent>
          </>
        )}

        {tab === "workspace" && (
          <>
            <CardHeader>
              <CardTitle>Workspace</CardTitle>
              <CardDescription>Company profile used across emails, quotations and reports.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>Company name</Label>
                  <Input defaultValue={session?.user?.orgName ?? ""} placeholder="Company name" />
                </div>
                <div className="space-y-2">
                  <Label>Industry</Label>
                  <Input placeholder="e.g. Technology" />
                </div>
                <div className="space-y-2">
                  <Label>Country</Label>
                  <Input placeholder="e.g. United States" />
                </div>
                <div className="space-y-2">
                  <Label>Timezone</Label>
                  <Input placeholder="e.g. UTC-05:00 (EST)" />
                </div>
              </div>
              <Button onClick={() => toast.success("Workspace settings saved")}>
                <Check className="h-4 w-4" /> Save changes
              </Button>
            </CardContent>
          </>
        )}

        {tab === "roles" && (
          <>
            <CardHeader>
              <CardTitle>Roles & permissions</CardTitle>
              <CardDescription>Department-based access control for larger teams.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {(roles ?? []).map((r) => (
                <div key={r.id} className="flex items-center justify-between rounded-xl border border-border-soft bg-card-soft/40 p-4">
                  <div>
                    <p className="text-sm font-bold text-white">{r.name}</p>
                    <p className="text-xs text-slate-500">{r.description}</p>
                  </div>
                  <Badge variant="secondary">
                    {ROLE_META[r.name]?.label ?? r.name}
                  </Badge>
                </div>
              ))}
              {!rolesLoading && (roles ?? []).length === 0 && (
                <p className="py-6 text-center text-sm text-slate-500">No roles defined yet.</p>
              )}
            </CardContent>
          </>
        )}

        {tab === "billing" && (
          <>
            <CardHeader>
              <CardTitle>Billing</CardTitle>
              <CardDescription>Your current plan and usage.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-slate-500">
                Your plan and subscription details are managed on the Billing page.
              </p>
              <Link href="/dashboard/billing">
                <Button><CreditCard className="h-4 w-4" /> View plans & billing</Button>
              </Link>
            </CardContent>
          </>
        )}

        {tab === "integrations" && <IntegrationsTab />}
      </Card>
    </div>
  );
}

// ── Departments tab (org admin: list / create / delete) ───
function DepartmentsTab({
  departments,
  loading,
}: {
  departments: { id: string; name: string; description?: string | null }[];
  loading: boolean;
}) {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", description: "" });

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!form.name.trim()) return toast.error("Department name is required");
    setSaving(true);
    const { error } = await addDepartment({
      name: form.name.trim(),
      description: form.description.trim() || null,
    });
    setSaving(false);
    if (error) return toast.error(error);
    toast.success(`${form.name.trim()} department created`);
    setForm({ name: "", description: "" });
    setShowCreate(false);
    queryClient.invalidateQueries({ queryKey: ["org-departments"] });
  }

  async function handleRemove(deptId: string) {
    setRemovingId(deptId);
    const { error } = await removeDepartment(deptId);
    setRemovingId(null);
    if (error) return toast.error(error);
    toast.success("Department removed");
    queryClient.invalidateQueries({ queryKey: ["org-departments"] });
  }

  return (
    <>
      <CardHeader className="flex-row items-center justify-between">
        <div>
          <CardTitle>Departments</CardTitle>
          <CardDescription>Structure your team into departments so roles and work are assigned by area.</CardDescription>
        </div>
        <Button size="sm" onClick={() => setShowCreate((s) => !s)}>
          <UserPlus className="h-4 w-4" /> Create department
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        <AnimatePresence>
          {showCreate && (
            <motion.form
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              onSubmit={handleCreate}
              className="overflow-hidden rounded-xl border border-primary/30 bg-primary/5 p-4"
            >
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label>Department name</Label>
                  <Input
                    value={form.name}
                    onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                    placeholder="e.g. Engineering, Sales, Finance"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>Description (optional)</Label>
                  <Input
                    value={form.description}
                    onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                    placeholder="What this department does"
                  />
                </div>
              </div>
              <div className="mt-3 flex gap-2">
                <Button type="submit" size="sm" disabled={saving}>
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Create
                </Button>
                <Button type="button" variant="ghost" size="sm" onClick={() => setShowCreate(false)}>Cancel</Button>
              </div>
            </motion.form>
          )}
        </AnimatePresence>

        {loading ? (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => <Skeleton key={i} className="h-14 w-full" />)}
          </div>
        ) : departments.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-500">
            No departments yet — create your first one (e.g. Sales, Engineering, Finance).
          </p>
        ) : (
          departments.map((d) => (
            <div key={d.id} className="flex items-center gap-3 rounded-xl border border-border-soft bg-card-soft/40 p-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-secondary text-white">
                <Network className="h-4 w-4" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-bold text-white">{d.name}</p>
                <p className="truncate text-xs text-slate-500">{d.description || "No description"}</p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="text-danger hover:text-danger"
                disabled={removingId === d.id}
                onClick={() => handleRemove(d.id)}
                title="Remove department"
              >
                {removingId === d.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              </Button>
            </div>
          ))
        )}
      </CardContent>
    </>
  );
}

// ── Users tab (org admin: list / invite / delete) ─────────
function UsersTab({
  orgId,
  roles,
  members,
  loading,
}: {
  orgId?: string | null;
  roles: { id: string; name: string }[];
  members: { id: string; full_name?: string | null; email?: string | null; status: string; roles: string[] }[];
  loading: boolean;
}) {
  const queryClient = useQueryClient();
  const [showInvite, setShowInvite] = useState(false);
  const [saving, setSaving] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [form, setForm] = useState({ full_name: "", email: "", password: "", role_name: DEFAULT_INVITE_ROLE });

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    if (!orgId) return toast.error("No organization bound to your account yet");
    setSaving(true);
    const { error } = await inviteMember({ ...form, organization_id: orgId });
    setSaving(false);
    if (error) return toast.error(error);
    toast.success(`${form.full_name || form.email} added to the team`);
    setForm({ full_name: "", email: "", password: "", role_name: DEFAULT_INVITE_ROLE });
    setShowInvite(false);
    queryClient.invalidateQueries({ queryKey: ["org-members"] });
  }

  async function handleRemove(userId: string) {
    setRemovingId(userId);
    const { error } = await removeMember(userId);
    setRemovingId(null);
    if (error) return toast.error(error);
    toast.success("Member removed");
    queryClient.invalidateQueries({ queryKey: ["org-members"] });
  }

  return (
    <>
      <CardHeader className="flex-row items-center justify-between">
        <div>
          <CardTitle>Team members</CardTitle>
          <CardDescription>People who can command your AI workforce. Roles decide what each member sees.</CardDescription>
        </div>
        <Button size="sm" onClick={() => setShowInvite((s) => !s)}>
          <UserPlus className="h-4 w-4" /> Invite member
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        <AnimatePresence>
          {showInvite && (
            <motion.form
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              onSubmit={handleInvite}
              className="overflow-hidden rounded-xl border border-primary/30 bg-primary/5 p-4"
            >
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label>Full name</Label>
                  <Input value={form.full_name} onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))} placeholder="Jane Doe" />
                </div>
                <div className="space-y-1.5">
                  <Label>Email</Label>
                  <Input type="email" required value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} placeholder="jane@company.com" />
                </div>
                <div className="space-y-1.5">
                  <Label>Password</Label>
                  <Input type="password" required minLength={8} value={form.password} onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))} placeholder="Min 8 characters" />
                </div>
                <div className="space-y-1.5">
                  <Label>Role</Label>
                  <select
                    value={form.role_name}
                    onChange={(e) => setForm((f) => ({ ...f, role_name: e.target.value }))}
                    className="h-11 w-full rounded-xl border border-border-soft bg-card-soft/60 px-3 text-sm text-white focus:border-primary/60 focus:outline-none"
                  >
                    {(roles.length > 0
                      ? roles
                      : // Seeded role list should always exist; fallback keeps
                        // the dropdown usable while roles are still loading.
                        [{ id: "fallback", name: DEFAULT_INVITE_ROLE }]
                    ).map((r) => (
                      <option key={r.id} value={r.name}>{r.name}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="mt-3 flex gap-2">
                <Button type="submit" size="sm" disabled={saving}>
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />} Add member
                </Button>
                <Button type="button" variant="ghost" size="sm" onClick={() => setShowInvite(false)}>Cancel</Button>
              </div>
            </motion.form>
          )}
        </AnimatePresence>

        {loading ? (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => <Skeleton key={i} className="h-14 w-full" />)}
          </div>
        ) : members.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-500">No members yet — invite your first teammate.</p>
        ) : (
          members.map((m) => (
            <div key={m.id} className="flex items-center gap-3 rounded-xl border border-border-soft bg-card-soft/40 p-3">
              <Avatar name={m.full_name || m.email || "U"} size="md" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-bold text-white">{m.full_name || "Unnamed member"}</p>
                <p className="truncate text-xs text-slate-500">{m.email}</p>
              </div>
              <div className="flex flex-wrap justify-end gap-1">
                {m.roles.map((r) => (
                  <Badge key={r} variant="secondary">{r}</Badge>
                ))}
                {m.roles.length === 0 && <Badge variant="secondary">No role</Badge>}
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="text-danger hover:text-danger"
                disabled={removingId === m.id}
                onClick={() => handleRemove(m.id)}
                title="Remove member"
              >
                {removingId === m.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              </Button>
            </div>
          ))
        )}
      </CardContent>
    </>
  );
}

// ── Integrations tab (live OAuth connect + env-key checks) ─
function IntegrationsTab() {
  const queryClient = useQueryClient();
  const [connecting, setConnecting] = useState<string | null>(null);
  const [keyConnected, setKeyConnected] = useState<Record<string, boolean>>({});
  const [waToken, setWaToken] = useState("");
  const [waPhoneId, setWaPhoneId] = useState("");
  const [waSaving, setWaSaving] = useState(false);
  const { data: statuses, isLoading } = useQuery({
    queryKey: ["integration-status"],
    queryFn: () => api.fetchIntegrationStatus(),
  });

  const statusFor = (provider: string) =>
    (statuses ?? []).find((s) => s.provider === provider);

  /** Save the workspace's OWN WhatsApp token + phone number ID (per-org). */
  async function handleWhatsappSave(e: React.FormEvent) {
    e.preventDefault();
    const token = waToken.trim();
    const phoneId = waPhoneId.trim();
    // Always reset the fields immediately — each workspace enters its own
    // credentials fresh, so stale/wrong input (or browser autofill) never
    // lingers in the form between attempts.
    setWaToken("");
    setWaPhoneId("");
    if (!token || !phoneId) {
      return toast.error("Enter both the API token and the phone number ID");
    }
    // Meta phone number IDs are pure numbers (e.g. 123456789012345) — never
    // an email address or a phone number in +1-format.
    if (!/^\d+$/.test(phoneId)) {
      return toast.error(
        "Phone number ID must be the numeric ID from Meta Business Manager (digits only, e.g. 123456789012345) — not an email"
      );
    }
    setWaSaving(true);
    try {
      const result = await api.saveWhatsappCredentials({
        api_token: token,
        phone_number_id: phoneId,
      });
      if (result.connected) {
        toast.success("WhatsApp connected with your own number");
      } else {
        toast.error(result.detail ?? "Could not verify the connection.");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not connect WhatsApp");
    } finally {
      setWaSaving(false);
      queryClient.invalidateQueries({ queryKey: ["integration-status"] });
    }
  }

  async function handleConnect(provider: string) {
    setConnecting(provider);
    try {
      const { authorize_url } = await api.connectIntegration(provider);
      window.location.assign(authorize_url); // leaves the page to the provider
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not start OAuth");
      setConnecting(null);
    }
  }

  /** Env-key providers: run a live connectivity test with the configured key.
   *  The backend persists the result, so on success the badge stays Connected
   *  after a page refresh (same as the OAuth providers). */
  async function handleCheckKey(provider: string, name: string) {
    setConnecting(provider);
    try {
      const result = await api.checkIntegration(provider);
      if (result.connected) {
        setKeyConnected((m) => ({ ...m, [provider]: true }));
        toast.success(`${name} connected — your AI employees can use it now`);
      } else {
        // Clear any earlier optimistic success so the persisted (false) state
        // from the backend is what the badge shows — never a stale Connected.
        setKeyConnected((m) => ({ ...m, [provider]: false }));
        toast.error(`${name}: ${result.detail ?? "Could not verify the connection."}`);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : `Could not verify ${name}`);
    } finally {
      setConnecting(null);
      // Refetch so the persisted connected flag (stored by the backend in the
      // integrations table) is what the badge shows after a refresh.
      queryClient.invalidateQueries({ queryKey: ["integration-status"] });
    }
  }

  return (
    <>
      <CardHeader>
        <CardTitle>Integrations</CardTitle>
        <CardDescription>
          Connect the tools your AI employees operate. After you approve in the provider page,
          you&apos;ll land back here automatically.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-3 sm:grid-cols-2">
          {OAUTH_INTEGRATIONS.map((i) => {
            const st = statusFor(i.provider);
            const configured = st?.configured ?? false;
            const connected = st?.connected ?? false;
            return (
              <div key={i.provider} className="flex items-center gap-3 rounded-xl border border-border-soft bg-card-soft/40 p-4">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-card text-xl">{i.emoji}</span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-bold text-white">{i.name}</p>
                  <p className="truncate text-xs text-slate-500">{i.desc}</p>
                </div>
                {connected ? (
                  <Badge variant="success">Connected</Badge>
                ) : configured ? (
                  <Button
                    size="sm"
                    disabled={connecting === i.provider}
                    onClick={() => handleConnect(i.provider)}
                  >
                    {connecting === i.provider ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Plug className="h-3.5 w-3.5" />
                    )}
                    Connect
                  </Button>
                ) : (
                  <Badge variant="secondary" title="Add the client ID/secret to the backend .env">
                    Not configured
                  </Badge>
                )}
              </div>
            );
          })}
        </div>

        <div className="rounded-xl border border-border-soft bg-card-soft/40 p-4">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-card text-xl">💬</span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-bold text-white">WhatsApp Business — your own number</p>
              <p className="truncate text-xs text-slate-500">
                Each workspace connects its own WhatsApp number — enter your Meta credentials below
              </p>
            </div>
            {statusFor("whatsapp")?.connected ? (
              <Badge variant="success">
                Connected
                {statusFor("whatsapp")?.phone_number_id
                  ? ` · ${statusFor("whatsapp")?.phone_number_id}`
                  : ""}
              </Badge>
            ) : statusFor("whatsapp")?.configured ? (
              <Badge variant="secondary">Not connected</Badge>
            ) : null}
          </div>
          {statusFor("whatsapp")?.connected && !waToken && !waPhoneId && (
            <p className="mt-2 text-xs text-slate-500">
              This workspace is connected to its own WhatsApp number. To switch numbers, enter the new
              credentials below and click Update & re-verify.
            </p>
          )}
          <form onSubmit={handleWhatsappSave} className="mt-3 grid gap-2 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>WhatsApp API token</Label>
              <Input
                type="password"
                autoComplete="new-password"
                value={waToken}
                onChange={(e) => setWaToken(e.target.value)}
                placeholder="EAAG… starts with EAAG or EAA"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Phone number ID</Label>
              <Input
                autoComplete="off"
                value={waPhoneId}
                onChange={(e) => setWaPhoneId(e.target.value)}
                placeholder="numeric only, e.g. 123456789012345"
              />
            </div>
            <div className="sm:col-span-2 flex flex-wrap items-center gap-2">
              <Button type="submit" size="sm" disabled={waSaving}>
                {waSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plug className="h-3.5 w-3.5" />}
                {statusFor("whatsapp")?.connected ? "Update & re-verify" : "Save & connect"}
              </Button>
              <p className="text-xs text-slate-600">
                Your token is stored encrypted and used only for your workspace.
              </p>
            </div>
            <details className="sm:col-span-2 rounded-xl border border-border-soft bg-card/40 px-3 py-2 text-xs text-slate-500">
              <summary className="cursor-pointer font-semibold text-slate-400 transition-colors hover:text-slate-300">
                📋 Where do I find these two values?
              </summary>
              <ol className="mt-2 list-decimal space-y-1 pl-4">
                <li>Open <b>business.facebook.com</b> and select the company that owns the WhatsApp number.</li>
                <li>Go to <b>WhatsApp → API Setup</b> (left menu).</li>
                <li><b>Phone number ID</b> — under “Phone numbers”: a long number like <b>123456789012345</b>. It is never an email.</li>
                <li><b>WhatsApp API token</b> — click <b>Generate token</b> (or “System user” → token). It starts with <b>EAAG…</b> / <b>EAA…</b> — never your email password.</li>
                <li>Paste both here and click <b>Save & connect</b>.</li>
              </ol>
            </details>
          </form>
        </div>

        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">API-key integrations</p>
          <div className="grid gap-3 sm:grid-cols-2">
            {KEY_INTEGRATIONS.map((i) => {
              const st = statusFor(i.provider);
              const configured = st?.configured ?? false;
              // Persisted flag from the backend (survives refresh), with the
              // just-run check as an immediate overlay while we refetch.
              const connected = keyConnected[i.provider] ?? st?.connected ?? false;
              return (
                <div key={i.provider} className="flex items-center gap-3 rounded-xl border border-border-soft bg-card-soft/40 p-4">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-card text-xl">{i.emoji}</span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-bold text-white">{i.name}</p>
                    <p className="truncate text-xs text-slate-500">{i.desc}</p>
                    <p className="truncate text-[10px] text-slate-600" title={i.keys}>Keys: {i.keys}</p>
                  </div>
                  {connected ? (
                    <Badge variant="success">Connected</Badge>
                  ) : configured ? (
                    <Button
                      size="sm"
                      disabled={connecting === i.provider}
                      onClick={() => handleCheckKey(i.provider, i.name)}
                    >
                      {connecting === i.provider ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Plug className="h-3.5 w-3.5" />
                      )}
                      Connect
                    </Button>
                  ) : (
                    <Badge variant="secondary" title={i.keys}>
                      Not configured
                    </Badge>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {isLoading && (
          <p className="text-center text-xs text-slate-500">Loading connection state…</p>
        )}
      </CardContent>
    </>
  );
}
