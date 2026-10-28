"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Workflow as WorkflowIcon, Zap } from "lucide-react";
import { Badge, StatusDot } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchWorkflows } from "@/services/data";
import { motion } from "framer-motion";

const ACTION_LABELS: Record<string, string> = {
  generate_receipt: "Generate Receipt",
  update_crm: "Update CRM",
  notify_sales: "Notify Sales Team",
  send_thank_you_email: "Send Thank You Email",
  schedule_follow_up: "Schedule Follow-up",
  classify_lead: "Classify Lead",
  create_task: "Create Task",
  send_welcome_email: "Send Welcome Email",
  send_reminder: "Send Reminder",
  notify_finance: "Notify Finance",
};

export default function WorkflowsPage() {
  const { data, isLoading } = useQuery({ queryKey: ["workflows"], queryFn: fetchWorkflows });
  const workflows = data?.source === "db" ? data.items : [];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm font-semibold text-primary-soft">Automation engine</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-white md:text-3xl">Workflows</h1>
          <p className="mt-1 text-sm text-slate-400">
            Chain triggers and actions so your AI workforce handles entire processes hands-free.
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {[1, 2].map((i) => <Skeleton key={i} className="h-56" />)}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {workflows.map((wf, idx) => {
            const actions = Array.isArray(wf.actions) ? (wf.actions as { type: string }[]) : [];
            return (
              <motion.div
                key={wf.id}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: idx * 0.08 }}
                whileHover={{ y: -4 }}
              >
                <Card className="h-full overflow-hidden">
                  <CardHeader>
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-2.5">
                        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-accent">
                          <WorkflowIcon className="h-4.5 w-4.5 text-white" />
                        </div>
                        <div>
                          <CardTitle>{wf.name ?? "Untitled workflow"}</CardTitle>
                          <CardDescription className="flex items-center gap-1.5 mt-0.5">
                            <Zap className="h-3 w-3" /> Trigger: {String((wf.trigger as Record<string, unknown> | null)?.event ?? "manual")}
                          </CardDescription>
                        </div>
                      </div>
                      <Badge variant={wf.active === false ? "secondary" : "success"}>
                        <StatusDot color={wf.active === false ? "#64748b" : "#22c55e"} />
                        {wf.active === false ? "Paused" : "Active"}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded-lg bg-accent/15 border border-accent/30 px-2.5 py-1 text-xs font-bold text-cyan-300">
                        {String((wf.trigger as Record<string, unknown> | null)?.event ?? "manual")}
                      </span>
                      <ArrowRight className="h-3.5 w-3.5 text-slate-500" />
                      {actions.map((a, i) => (
                        <div key={i} className="flex items-center gap-2">
                          <span className="rounded-lg bg-card-soft border border-border-soft px-2.5 py-1 text-xs font-semibold text-slate-200">
                            {ACTION_LABELS[a.type] ?? a.type}
                          </span>
                          {i < actions.length - 1 && <ArrowRight className="h-3 w-3 text-slate-600" />}
                        </div>
                      ))}
                    </div>
                    <p className="mt-4 text-xs text-slate-500">
                      {actions.length} automated steps · runs on every trigger event
                    </p>
                  </CardContent>
                </Card>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
