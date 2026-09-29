import type { PluginClientContext } from "@getpaseo/plugin/client";
import { UsageSurface } from "./client/usage-surface";

const PANEL_ID = "usage";

export default function contribute(client: PluginClientContext) {
  const removePanel = client.addWorkspacePanel({
    id: PANEL_ID,
    title: "사용량",
    icon: "Gauge",
    context: "workspace",
    locations: ["explorer"],
    Component: UsageSurface,
  });

  const pillStops = new Map<string, () => void>();
  let cleanedUp = false;
  type Agent = Awaited<ReturnType<typeof client.paseo.agents.list>>["entries"][number]["agent"];
  const registerAgentPill = (agent: Agent) => {
    const { id: agentId, workspaceId } = agent;
    if (cleanedUp || workspaceId == null || pillStops.has(agentId)) {
      return;
    }

    const registration = client.addComposerPill({
      id: "usage-pill",
      workspaceId,
      agentId,
      button: {
        title: "사용량",
        icon: "Gauge",
        label: "사용량",
        behavior: {
          kind: "action",
          onPress: () => client.openPanel(PANEL_ID, { workspaceId, location: "explorer" }),
        },
      },
    });
    pillStops.set(agentId, () => registration.remove());
  };

  const stopSubscription = client.paseo.agents.subscribe((update) => {
    if (update.kind === "remove") {
      pillStops.get(update.agentId)?.();
      pillStops.delete(update.agentId);
      return;
    }
    registerAgentPill(update.agent);
  });

  void client.paseo.agents.list().then(
    (listed) => {
      if (cleanedUp) {
        return;
      }
      for (const entry of listed.entries) {
        registerAgentPill(entry.agent);
      }
    },
    () => {},
  );

  return () => {
    cleanedUp = true;
    stopSubscription();
    for (const stop of pillStops.values()) {
      stop();
    }
    pillStops.clear();
    removePanel();
  };
}
