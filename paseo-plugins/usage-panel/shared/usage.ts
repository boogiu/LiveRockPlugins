import { defineRpc, type RpcOutput } from "@getpaseo/plugin";
import { z } from "zod";

/** 세션 목록과 "오늘" 합계를 내려고 읽는 기간. 이 날수 안에 수정된 로그 파일만 읽는다. */
export const RECENT_DAYS = 7;

const tokenAmount = z.object({
  input: z.number(),
  output: z.number(),
  total: z.number(),
});

// 숫자와 식별자만 내보낸다. 대화 원문이 클라이언트로 나가지 않도록 문자열 필드를 여기 추가하지 않는다.
const providerTokens = z.discriminatedUnion("status", [
  z.object({
    status: z.literal("ok"),
    today: tokenAmount,
    sessions: z.array(
      z.object({
        id: z.string(),
        firstAt: z.string(),
        lastAt: z.string(),
        total: z.number(),
      }),
    ),
  }),
  z.object({ status: z.literal("no-logs") }),
  // 오류 원문은 서버 로그(Settings → Plugins → Logs)에만 남기고 응답에는 실패 사실만 싣는다.
  z.object({ status: z.literal("error") }),
]);

export const tokenUsageRpc = defineRpc({
  name: "usage.tokens",
  input: z.object({}),
  output: z.object({
    generatedAt: z.string(),
    codex: providerTokens,
    claude: providerTokens,
  }),
});

export type TokenAmount = z.infer<typeof tokenAmount>;
export type ProviderTokens = z.infer<typeof providerTokens>;
export type TokenUsage = RpcOutput<typeof tokenUsageRpc>;
