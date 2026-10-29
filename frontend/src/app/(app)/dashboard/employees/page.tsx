"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Search } from "lucide-react";
import Link from "next/link";
import { EmployeeCard } from "@/components/ai/employee-card";
import { ModuleWidgets } from "@/components/dashboard/module-widgets";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchAIEmployees } from "@/services/data";

const ROLES = ["All", "Marketing", "Sales", "Support", "Finance", "HR", "Executive"];

export default function AIEmployeesPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["ai-employees"],
    queryFn: fetchAIEmployees,
  });
  const [filter, setFilter] = useState("All");
  const [query, setQuery] = useState("");

  const employees = data?.source === "db" ? data.items : [];
  const filtered = employees.filter((e) => {
    const matchesRole = filter === "All" || e.role.includes(filter);
    const q = query.toLowerCase();
    const matchesQuery = !q || e.name.toLowerCase().includes(q) || e.role.toLowerCase().includes(q);
    return matchesRole && matchesQuery;
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm font-semibold text-primary-soft">Your workforce</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-white md:text-3xl">
            AI Employees
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Specialized agents that execute real business work — emails, CRM, invoices, meetings.
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap gap-2">
          {ROLES.map((r) => (
            <button
              key={r}
              onClick={() => setFilter(r)}
              className={`rounded-full px-3.5 py-1.5 text-xs font-bold transition-all duration-200 cursor-pointer ${
                filter === r
                  ? "bg-gradient-to-r from-primary to-secondary text-white shadow-lg shadow-primary/25"
                  : "border border-border-soft bg-card text-slate-400 hover:text-white hover:border-primary/40"
              }`}
            >
              {r}
            </button>
          ))}
        </div>
        <div className="relative w-full sm:w-64">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <Input placeholder="Search employees…" className="pl-10" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
      </div>

      {/* Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => <Skeleton key={i} className="h-72" />)}
        </div>
      ) : isError ? (
        <div className="rounded-2xl border border-danger/30 bg-danger/10 p-8 text-center">
          <p className="font-semibold text-danger">Failed to load employees</p>
          <p className="mt-1 text-sm text-slate-400">{(error as Error).message}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((emp, i) => (
            <Link key={emp.id} href={`/dashboard/employees/${emp.id}`}>
              <EmployeeCard employee={emp} index={i} />
            </Link>
          ))}
          {filtered.length === 0 && (
            <p className="col-span-full rounded-2xl border border-border-soft bg-card-soft/40 p-8 text-center text-sm text-slate-500">
              No AI employees here yet.
            </p>
          )}
        </div>
      )}

      {/* Module widgets — gated by the org's enabled modules */}
      <ModuleWidgets dashboardName="AI Employees Dashboard" />
    </div>
  );
}
