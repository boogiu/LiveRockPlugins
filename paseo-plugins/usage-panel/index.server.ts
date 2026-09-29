import type { PluginServerContext } from "@getpaseo/plugin/server";
import { readLimitUsage } from "./server/limits";
import { readTokenUsage } from "./server/usage";
import { limitUsageRpc } from "./shared/limits";
import { tokenUsageRpc } from "./shared/usage";

export default function contribute(server: PluginServerContext) {
  server.handle(limitUsageRpc, readLimitUsage);
  server.handle(tokenUsageRpc, readTokenUsage);
  return () => {};
}
