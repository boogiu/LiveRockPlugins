import { homedir } from "node:os";
import { join } from "node:path";
import { RECENT_DAYS, type ProviderTokens, type TokenUsage } from "../shared/usage";
import { collectClaude, collectCodex, localRange, type Collected } from "./tokens";

const MAX_SESSIONS = 20;

export async function readTokenUsage(): Promise<TokenUsage> {
  const now = new Date();
  const range = localRange(now, RECENT_DAYS);
  const home = homedir();
  // 한쪽이 실패해도 다른 쪽은 보여야 하므로 provider마다 따로 받는다.
  const [codex, claude] = await Promise.all([
    summarize("codex", () => collectCodex(join(home, ".codex"), range), range.sinceMs),
    summarize("claude", () => collectClaude(join(home, ".claude", "projects"), range), range.sinceMs),
  ]);
  return { generatedAt: now.toISOString(), codex, claude };
}

async function summarize(
  provider: string,
  collect: () => Promise<Collected | null>,
  sinceMs: number,
): Promise<ProviderTokens> {
  try {
    const collected = await collect();
    if (collected == null) {
      return { status: "no-logs" };
    }
    const sessions = collected.sessions
      .filter((session) => session.lastMs >= sinceMs && session.total > 0)
      .sort((left, right) => right.lastMs - left.lastMs)
      .slice(0, MAX_SESSIONS)
      .map((session) => ({
        id: session.id,
        firstAt: new Date(session.firstMs).toISOString(),
        lastAt: new Date(session.lastMs).toISOString(),
        total: session.total,
      }));
    return { status: "ok", today: collected.today, sessions };
  } catch (error) {
    console.error(`[usage-panel] ${provider} token scan failed:`, error);
    return { status: "error" };
  }
}
