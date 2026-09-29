import type { PluginHandlerContext } from "@getpaseo/plugin/server";
import type { LimitUsage, ProviderLimits } from "../shared/limits";

const PROVIDER_IDS = ["codex", "claude"] as const;

// 한도는 데몬이 캐시한 listUsage() 값이다. 서버에서 불러야 실패 원문이 Settings → Plugins → Logs에 남는다.
export async function readLimitUsage(_input: unknown, { paseo }: PluginHandlerContext): Promise<LimitUsage> {
  let result: Awaited<ReturnType<typeof paseo.providers.listUsage>>;
  try {
    result = await paseo.providers.listUsage();
  } catch (error) {
    console.error("[usage-panel] listUsage failed:", error);
    const failed: ProviderLimits = { status: "error", planLabel: null, windows: [] };
    return { codex: failed, claude: failed };
  }

  const pick = (providerId: (typeof PROVIDER_IDS)[number]): ProviderLimits | null => {
    const usage = result.providers.find((entry) => entry.providerId === providerId);
    if (usage == null) {
      return null;
    }
    if (usage.status === "error") {
      console.error(`[usage-panel] ${providerId} limit error:`, usage.error);
    }
    return {
      status: usage.status,
      planLabel: usage.planLabel,
      windows: usage.windows.map((limit) => ({
        id: limit.id,
        label: limit.label,
        usedPct: limit.usedPct ?? null,
        remainingPct: limit.remainingPct ?? null,
        resetsAt: limit.resetsAt ?? null,
        tone: limit.tone ?? null,
      })),
    };
  };
  return { codex: pick("codex"), claude: pick("claude") };
}
