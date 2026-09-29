import { usePaseo } from "@getpaseo/plugin/client";
import { useEffect, useState } from "react";
import { runningProviders, type AgentActivity } from "./agent-activity";

export function useAgentActivity() {
  const paseo = usePaseo();
  const [running, setRunning] = useState(() => runningProviders([]));

  useEffect(() => {
    const agents = new Map<string, AgentActivity>();
    const pending = new Map<string, AgentActivity | null>();
    let loaded = false;
    let disposed = false;
    let releaseDirectory: (() => void) | null = null;
    const apply = (id: string, agent: AgentActivity | null) => {
      if (agent == null) agents.delete(id);
      else agents.set(id, agent);
    };

    const stopSubscription = paseo.agents.subscribe((update) => {
      const id = update.kind === "remove" ? update.agentId : update.agent.id;
      const agent = update.kind === "remove" ? null : update.agent;
      if (!loaded) {
        pending.set(id, agent);
        return;
      }
      apply(id, agent);
      setRunning(runningProviders(agents.values()));
    });

    void (async () => {
      try {
        let cursor: string | undefined;
        let firstPage = true;
        do {
          const listed = await paseo.agents.list({
            filter: { statuses: ["running"] },
            page: { limit: 100, cursor },
            ...(firstPage ? { subscribe: {} } : {}),
          });
          if (firstPage) {
            const subscription = "subscription" in listed ? listed.subscription : null;
            if (subscription != null && typeof subscription === "object" && "release" in subscription) {
              const releaseMethod = subscription.release;
              if (typeof releaseMethod === "function") {
                const release = () => { void releaseMethod.call(subscription); };
                if (disposed) release();
                else releaseDirectory = release;
              }
            }
            firstPage = false;
          }
          if (disposed) return;
          for (const entry of listed.entries) {
            agents.set(entry.agent.id, entry.agent);
          }
          cursor = listed.pageInfo.nextCursor ?? undefined;
        } while (cursor);
      } catch {
        // Live updates remain available if the initial list cannot be read.
      }
      if (disposed) return;
      for (const [id, agent] of pending) apply(id, agent);
      loaded = true;
      setRunning(runningProviders(agents.values()));
    })();

    return () => {
      disposed = true;
      stopSubscription();
      releaseDirectory?.();
    };
  }, [paseo]);

  return running;
}
