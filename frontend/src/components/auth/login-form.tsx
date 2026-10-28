"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Mail, Lock, ArrowRight, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  fetchUserOrgId,
  fetchUserRoles,
  PENDING_WORKSPACE_KEY,
  signIn,
} from "@/hooks/use-session";
import { homePathForRoles } from "@/lib/roles";
import { supabase } from "@/lib/supabase/client";
import { api } from "@/lib/api/client";
import { toast } from "sonner";
import { motion } from "framer-motion";

export function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [sendingReset, setSendingReset] = useState(false);
  const [resetSent, setResetSent] = useState(false);

  /**
   * Finish a workspace whose org could not be created at signup because email
   * confirmation delayed the session. Returns whether the org was created and
   * any error that prevented it. The pending payload is kept on failure so the
   * next sign-in can retry.
   */
  async function finishPendingWorkspace(userId: string): Promise<{
    created: boolean;
    error: string | null;
  }> {
    const raw = localStorage.getItem(PENDING_WORKSPACE_KEY);
    if (!raw) return { created: false, error: null };
    try {
      const orgId = await fetchUserOrgId(userId);
      if (orgId) {
        // Already in an org — nothing to create.
        localStorage.removeItem(PENDING_WORKSPACE_KEY);
        return { created: false, error: null };
      }
      const workspace = JSON.parse(raw) as {
        name: string;
        slug: string;
        country: string;
        industry?: string;
      };
      await api.createOrganization(workspace);
      localStorage.removeItem(PENDING_WORKSPACE_KEY);
      return { created: true, error: null };
    } catch (err) {
      return { created: false, error: (err as Error).message || "Could not create your workspace" };
    }
  }

  /** Shared: sign in with Supabase, then redirect by the user's role. */
  async function signInAndRedirect(email: string, password: string, successMessage: string) {
    setLoading(true);
    try {
      await signIn(email, password);

      // Role-based redirect: Owners/Admins land on the dashboard, Employees on
      // their tasks. A user without roles yet (e.g. before workspace setup)
      // goes to the dashboard to finish onboarding.
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!session) return;
      const roles = await fetchUserRoles(session.user.id);

      // Signups delayed by email confirmation finish their workspace here.
      const { created, error: workspaceError } = await finishPendingWorkspace(
        session.user.id
      );
      if (created) {
        toast.success("Workspace created! Welcome aboard 🎉");
        router.push("/dashboard");
        return;
      }
      if (workspaceError) {
        toast.error(workspaceError);
        router.push(homePathForRoles(roles));
        return;
      }

      toast.success(successMessage);
      router.push(homePathForRoles(roles));
    } catch (err) {
      toast.error((err as Error).message || "Invalid credentials");
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await signInAndRedirect(email, password, "Welcome back!");
  }

  /** Send a Supabase password-recovery link to the entered email. */
  async function handleForgotPassword() {
    if (!email.trim()) {
      toast.error("Enter your email address first.");
      return;
    }
    setSendingReset(true);
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(email.trim(), {
        // The recovery link lands here; the page reads the token and lets the
        // user set a new password. Add this origin to Supabase → Auth → URL
        // Configuration → Redirect URLs for production.
        redirectTo: `${window.location.origin}/reset-password`,
      });
      if (error) throw error;
      setResetSent(true);
      toast.success("Password reset link sent — check your inbox.");
    } catch (err) {
      toast.error((err as Error).message || "Could not send the reset link");
    } finally {
      setSendingReset(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div className="space-y-2">
        <Label htmlFor="email">Email</Label>
        <div className="relative">
          <Mail className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <Input
            id="email"
            type="email"
            required
            placeholder="you@company.com"
            className="pl-10"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label htmlFor="password">Password</Label>
          <button
            type="button"
            onClick={handleForgotPassword}
            disabled={sendingReset}
            className="text-xs font-semibold text-primary-soft hover:text-white transition-colors cursor-pointer disabled:opacity-50"
          >
            {sendingReset ? "Sending…" : "Forgot password?"}
          </button>
        </div>
        <div className="relative">
          <Lock className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <Input
            id="password"
            type="password"
            required
            placeholder="••••••••"
            className="pl-10"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
      </div>

      <motion.div whileTap={{ scale: 0.98 }}>
        <Button type="submit" className="w-full" size="lg" disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <>Sign in <ArrowRight className="h-4 w-4" /></>}
        </Button>
      </motion.div>

      {resetSent && (
        <p className="rounded-xl border border-success/30 bg-success/10 px-4 py-3 text-xs text-green-300">
          Reset link sent to <span className="font-bold">{email.trim()}</span> — check your inbox, then
          use the link to set a new password.
        </p>
      )}

      <p className="text-center text-sm text-slate-500">
        Don&apos;t have an account?{" "}
        <button
          type="button"
          onClick={() => router.push("/register")}
          className="font-bold text-primary-soft hover:text-white transition-colors cursor-pointer"
        >
          Create workspace
        </button>
      </p>
    </form>
  );
}
