"use client";

import { useQuery } from "@tanstack/react-query";
import { Bot, Kanban, Workflow, MessageSquare, ArrowRight } from "lucide-react";
import Link from "next/link";
import { motion } from "framer-motion";
import { StatCard } from "@/components/dashboard/stat-card";
import { ActivityFeed } from "@/components/dashboard/activity-feed";
import { ModuleWidgets } from "@/components/dashboard/module-widgets";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchOrgStats, fetchTasks, PRIORITY_COLORS } from "@/services/data";
import { formatCompact, timeAgo } from "@/lib/utils";
import { useSession } from "@/hooks/use-session";

export default function DashboardPage() {
  const { data: session } = useSession();
  const { data: stats } = useQuery({ queryKey: ["org-stats"], queryFn: fetchOrgStats });
  const { data: tasks } = useQuery({ queryKey: ["tasks"], queryFn: fetchTasks });

  const taskItems = tasks?.source === "db" ? tasks.items : [];

  return (
    <div className="space-y-8">
      {/* Greeting */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm font-semibold text-primary-soft">Welcome back, {session?.user?.name ?? "Admin"}</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-white md:text-3xl">
            Your AI workforce is <span className="text-gradient">on duty</span>
          </h1>
        </div>
        <div className="flex gap-2">
          <Link href="/dashboard/chat?agent=master">
            <Button>
              <MessageSquare className="h-4 w-4" /> Delegate a task
            </Button>
          </Link>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="AI Employees" value={formatCompact(stats?.employees ?? 0)} icon={<Bot className="h-5 w-5" />} gradient="from-primary to-secondary" loading={!stats} />
        <StatCard label="Tasks Completed" value={formatCompact(stats?.tasks ?? 0)} icon={<Kanban className="h-5 w-5" />} gradient="from-secondary to-accent" loading={!stats} />
        <StatCard label="Active Workflows" value={formatCompact(stats?.workflows ?? 0)} icon={<Workflow className="h-5 w-5" />} gradient="from-accent to-primary" loading={!stats} />
        <StatCard label="AI Conversations" value={formatCompact(stats?.conversations ?? 0)} icon={<MessageSquare className="h-5 w-5" />} gradient="from-warning to-danger" loading={!stats} />
      </div>

      {/* Bottom row */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardTitle>Recent tasks</CardTitle>
              <CardDescription>Latest assignments your AI workforce handled</CardDescription>
            </div>
            <Link href="/dashboard/tasks" className="text-sm font-semibold text-primary-soft hover:text-white transition-colors inline-flex items-center gap-1">
              View all <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {taskItems.length === 0 ? (
                <p className="text-sm text-slate-500">No tasks yet — create one to see it here.</p>
              ) : (
                taskItems.slice(0, 5).map((t) => (
                  <motion.div
                    key={t.id}
                    whileHover={{ x: 4 }}
                    className="flex items-center gap-3 rounded-xl border border-border-soft bg-card-soft/40 p-3 transition-colors hover:border-primary/30"
                  >
                    <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: PRIORITY_COLORS[t.priority ?? "medium"] }} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold text-slate-100">{t.title}</p>
                      <p className="text-xs text-slate-500">{t.description ?? "No description"}</p>
                    </div>
                    <Badge variant={t.status === "done" ? "success" : t.status === "in_progress" ? "accent" : "secondary"}>
                      {t.status?.replace("_", " ")}
                    </Badge>
                    <span className="hidden text-xs text-slate-500 sm:block">{timeAgo(t.due_date ?? t.created_at)}</span>
                  </motion.div>
                ))
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Activity</CardTitle>
            <CardDescription>Latest CRM actions</CardDescription>
          </CardHeader>
          <CardContent><ActivityFeed /></CardContent>
        </Card>
      </div>

      {/* Module widgets — powered by the modules enabled for this org */}
      <ModuleWidgets dashboardName="Company Admin Dashboard" />
    </div>
  );
}
