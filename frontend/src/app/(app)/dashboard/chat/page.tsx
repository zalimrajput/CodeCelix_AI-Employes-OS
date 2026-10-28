"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Suspense, useState } from "react";
import { Bot, MessageSquare, Plus, Sparkles } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ChatInterface } from "@/components/ai/chat-interface";
import { fetchAIEmployees, fetchConversations, fetchMessages, createConversation } from "@/services/data";
import { employeeForAgent, agentDisplayName, agentForRoles, canPickAllAgents, AGENT_KEYS, type AgentKey } from "@/lib/agents";
import { cn, timeAgo } from "@/lib/utils";
import { useSession } from "@/hooks/use-session";
import { toast } from "sonner";

// useSearchParams must be rendered inside a <Suspense> boundary for static
// prerendering — this component keeps the rest of the page intact.
export default function ChatPage() {
  return (
    <Suspense fallback={<div className="flex h-full items-center justify-center text-sm text-slate-500">Loading chat…</div>}>
      <ChatPageInner />
    </Suspense>
  );
}

function ChatPageInner() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();
  const { data: convData, isLoading } = useQuery({ queryKey: ["conversations"], queryFn: fetchConversations });
  const { data: empData } = useQuery({ queryKey: ["ai-employees"], queryFn: fetchAIEmployees });
  const searchParams = useSearchParams();
  const agentParam = searchParams.get("agent");
  const employeeParam = searchParams.get("employee");
  const [activeId, setActiveId] = useState<string | null>(null);
  // Leadership-only agent picker (Super Admin / Company Admin / CEO): when set,
  // new conversations bind to this agent instead of the role/dashboard default.
  const [pickerAgent, setPickerAgent] = useState<AgentKey | "">("");
  const showAgentPicker = canPickAllAgents(session?.user?.roles);
  // No ?agent= / ?employee= → bind new conversations to the agent of the
  // logged-in user's own role (Sales Executive → AI Sales Assistant), not the
  // first AI employee.
  const defaultAgent = agentForRoles(session?.user?.roles);

  const createMutation = useMutation({
    mutationFn: async () => {
      const user = session?.user;
      // Bind the new conversation to the agent/employee requested by the
      // dashboard (?agent=sales → AI Sales Assistant, or ?employee=<id>);
      // fall back to the first employee.
      const targetEmp =
        employeeForAgent(employees, pickerAgent || null) ??
        employeeForAgent(employees, agentParam) ??
        (employeeParam ? employees.find((e) => e.id === employeeParam) : undefined) ??
        employeeForAgent(employees, defaultAgent) ??
        employees[0];
      if (!user || !user.orgId || !targetEmp) {
        throw new Error("Create a workspace and deploy an AI employee first.");
      }
      const conv = await createConversation({
        organization_id: user.orgId,
        user_id: user.id,
        ai_employee_id: targetEmp.id,
        title: "New conversation",
      });
      if (!conv) throw new Error("Could not create conversation in the database.");
      return conv;
    },
    onSuccess: (conv) => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      setActiveId(conv.id);
      toast.success("Conversation started — say hello!");
    },
    onError: (e) => {
      toast.info((e as Error).message);
      setActiveId(null);
    },
  });

  const conversations = convData?.source === "db" ? convData.items : [];
  const employees = empData?.source === "db" ? empData.items : [];
  const selected = conversations.find((c) => c.id === activeId) ?? conversations[0];
  const selectedEmp = employees.find((e) => e.id === selected?.ai_employee_id);
  // Agent requested by the landing dashboard (e.g. ?agent=sales), if any.
  // pickerAgent takes priority (explicit leadership choice) over both.
  const landingEmp =
    employeeForAgent(employees, pickerAgent || null) ??
    employeeForAgent(employees, agentParam) ??
    (employeeParam ? employees.find((e) => e.id === employeeParam) : undefined) ??
    employeeForAgent(employees, defaultAgent);
  const landingAgentName =
    landingEmp?.name ?? agentDisplayName(agentParam) ?? agentDisplayName(defaultAgent) ?? undefined;

  const { data: msgData } = useQuery({
    queryKey: ["messages", selected?.id],
    queryFn: () => (selected ? fetchMessages(selected.id) : Promise.resolve({ source: "db" as const, items: [] })),
    enabled: !!selected,
  });

  const messages = msgData?.source === "db" ? msgData.items : [];

  function handleNewChat() {
    createMutation.mutate();
  }

  return (
    <div className="flex h-[calc(100vh-8.5rem)] min-h-[480px] overflow-hidden rounded-2xl border border-border-soft bg-card/50 backdrop-blur-xl">
      {/* Conversations */}
      <aside className="hidden w-72 shrink-0 flex-col border-r border-border-soft sm:flex">
        <div className="flex items-center justify-between gap-2 border-b border-border-soft p-4">
          <h2 className="text-sm font-bold text-white">Conversations</h2>
          {showAgentPicker ? (
            <div className="flex items-center gap-1.5">
              <select
                aria-label="Pick AI agent for the next chat"
                value={pickerAgent}
                onChange={(e) => setPickerAgent(e.target.value as AgentKey | "")}
                className="max-w-[9rem] cursor-pointer rounded-lg border border-border-soft bg-card px-1.5 py-1 text-xs text-slate-200 outline-none focus:border-primary/50"
              >
                <option value="">Auto — default agent</option>
                {AGENT_KEYS.map((key) => (
                  <option key={key} value={key}>
                    {agentDisplayName(key) ?? key}
                  </option>
                ))}
              </select>
              <Button size="iconSm" onClick={handleNewChat} aria-label="New chat">
                <Plus className="h-4 w-4" />
              </Button>
            </div>
          ) : (
            <Button size="iconSm" onClick={handleNewChat} aria-label="New chat">
              <Plus className="h-4 w-4" />
            </Button>
          )}
        </div>
        <div className="flex-1 space-y-1 overflow-y-auto p-2 no-scrollbar">
          {isLoading ? (
            [1, 2, 3].map((i) => <Skeleton key={i} className="h-14 mx-1.5" />)
          ) : (
            conversations.map((c) => {
              const emp = employees.find((e) => e.id === c.ai_employee_id);
              const active = selected?.id === c.id;
              return (
                <button
                  key={c.id}
                  onClick={() => setActiveId(c.id)}
                  className={cn(
                    "w-full rounded-xl p-3 text-left transition-all cursor-pointer",
                    active ? "bg-gradient-to-r from-primary/20 to-secondary/20 border border-primary/30" : "hover:bg-card-soft"
                  )}
                >
                  <div className="flex items-center gap-2.5">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-secondary">
                      <Bot className="h-4 w-4 text-white" />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-white">{c.title ?? "Untitled"}</p>
                      <p className="text-xs text-slate-500">
                        {emp?.name ?? "AI Employee"} · {timeAgo(c.updated_at)}
                      </p>
                    </div>
                  </div>
                </button>
              );
            })
          )}
          {!isLoading && conversations.length === 0 && (
            <p className="px-3 py-6 text-center text-sm text-slate-500">No conversations yet.</p>
          )}
        </div>
      </aside>

      {/* Chat */}
      <div className="flex min-w-0 flex-1 flex-col">
        {selected ? (
          <ChatInterface
            employeeName={selectedEmp?.name ?? "AI Employee"}
            conversationTitle={selected.title ?? null}
            conversationId={selected.id}
            initialMessages={messages}
            onNewChat={handleNewChat}
          />
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-secondary shadow-2xl shadow-primary/30">
              <MessageSquare className="h-8 w-8 text-white" />
            </div>
            <div>
              <p className="text-lg font-bold text-white">Start a conversation</p>
              <p className="mt-1 max-w-sm text-sm text-slate-400">
                Delegate emails, quotations, CRM updates, reports and more to your AI employees.
              </p>
              {landingAgentName && (
                <p className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-semibold text-primary-soft">
                  <Sparkles className="h-3 w-3" /> Talking to {landingEmp?.name ?? landingAgentName}
                </p>
              )}
            </div>
            {showAgentPicker && (
              <select
                aria-label="Pick AI agent"
                value={pickerAgent}
                onChange={(e) => setPickerAgent(e.target.value as AgentKey | "")}
                className="cursor-pointer rounded-xl border border-border-soft bg-card px-3 py-2 text-sm text-slate-200 outline-none focus:border-primary/50"
              >
                <option value="">Auto — default agent</option>
                {AGENT_KEYS.map((key) => (
                  <option key={key} value={key}>
                    {agentDisplayName(key) ?? key}
                  </option>
                ))}
              </select>
            )}
            <Button onClick={handleNewChat}><Plus className="h-4 w-4" /> New conversation</Button>
          </div>
        )}
      </div>
    </div>
  );
}
