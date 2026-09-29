import { defineRpc, type RpcOutput } from "@getpaseo/plugin";
import { z } from "zod";

const limitWindow = z.object({
  id: z.string(),
  label: z.string(),
  usedPct: z.number().nullable(),
  remainingPct: z.number().nullable(),
  resetsAt: z.string().nullable(),
  tone: z.enum(["default", "ok", "warning", "danger"]).nullable(),
});

// 화면에 그릴 값만 싣는다. 오류 원문은 서버 로그(Settings → Plugins → Logs)에만 남기고 여기에는 상태만 싣는다.
const providerLimits = z.object({
  status: z.enum(["available", "unavailable", "error"]),
  planLabel: z.string().nullable(),
  windows: z.array(limitWindow),
});

/** 응답에 provider가 없으면 null이다. */
export const limitUsageRpc = defineRpc({
  name: "usage.limits",
  input: z.object({}),
  output: z.object({
    codex: providerLimits.nullable(),
    claude: providerLimits.nullable(),
  }),
});

export type LimitWindow = z.infer<typeof limitWindow>;
export type ProviderLimits = z.infer<typeof providerLimits>;
export type LimitUsage = RpcOutput<typeof limitUsageRpc>;
