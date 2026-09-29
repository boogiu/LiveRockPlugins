export type AgentActivity = {
  id: string;
  provider: string;
  status: string;
};

export function runningProviders(agents: Iterable<AgentActivity>) {
  const running = { codex: false, claude: false };
  for (const agent of agents) {
    if (agent.status === "running" && (agent.provider === "codex" || agent.provider === "claude")) {
      running[agent.provider] = true;
    }
  }
  return running;
}
