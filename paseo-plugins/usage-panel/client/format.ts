import type { LimitWindow, ProviderLimits } from "../shared/limits";
import type { ProviderTokens } from "../shared/usage";

/**
 * 한도 창의 화면 이름. Paseo는 codex의 7일 창에도 "Session"을 붙여 보내고 창 길이는 알려 주지 않으므로
 * codex 창에는 받은 이름을 쓰지 않는다. Claude는 관측된 id만 한국어 이름을 붙이고 나머지는 받은 이름 그대로 둔다.
 */
export function windowName(providerId: string, limit: LimitWindow): string {
  if (providerId === "codex") {
    return "사용 한도";
  }
  if (limit.id === "five_hour") {
    return "5시간 한도";
  }
  if (limit.id === "weekly") {
    return "주간 한도";
  }
  if (limit.id.startsWith("weekly_model_")) {
    const model = limit.label.split("·")[1]?.trim() || limit.id.slice("weekly_model_".length);
    return `주간 한도 (${model})`;
  }
  return limit.label;
}

export type Notice = { tone: "danger" | "muted"; text: string };

// 오류·빈 상태 문구. 오류 원문은 받지 않는다 — 원문은 진단 로그로만 보내고 화면에는 한국어 안내만 보인다.

/** 한도 카드에 창 목록 대신 보일 문구. 창 목록을 보일 수 있으면 null. */
export function limitNotice(usage: ProviderLimits | null | undefined, failed: boolean): Notice | null {
  if (failed || usage?.status === "error") {
    return { tone: "danger", text: "한도를 불러오지 못했습니다. 잠시 뒤 새로고침을 눌러 보세요." };
  }
  if (usage == null || usage.status === "unavailable" || usage.windows.length === 0) {
    return { tone: "muted", text: "이 로그인 방식에서는 한도를 볼 수 없습니다." };
  }
  return null;
}

/** 토큰 카드에 합계 대신 보일 문구. 합계를 보일 수 있으면 null. */
export function tokenNotice(name: string, tokens: ProviderTokens | undefined, failed: boolean): Notice | null {
  if (failed || tokens == null || tokens.status === "error") {
    return { tone: "danger", text: "이 PC의 사용 기록을 읽지 못했습니다." };
  }
  if (tokens.status === "no-logs") {
    return { tone: "muted", text: `이 PC에서 ${name}를 쓴 기록이 없습니다.` };
  }
  return null;
}

export function usedPercent(limit: LimitWindow): number | null {
  if (limit.usedPct != null) {
    return limit.usedPct;
  }
  return limit.remainingPct != null ? 100 - limit.remainingPct : null;
}

export function remainingPercent(limit: LimitWindow): number | null {
  if (limit.remainingPct != null) {
    return limit.remainingPct;
  }
  return limit.usedPct != null ? 100 - limit.usedPct : null;
}

/** 0%인 창은 아직 시작되지 않아 리셋 시각이 계속 밀리므로 시각 대신 "아직 사용하지 않음"을 보인다. */
export function resetText(limit: LimitWindow, nowMs: number): string {
  if (usedPercent(limit) === 0) {
    return "아직 사용하지 않음";
  }
  const resetsMs = parseTime(limit.resetsAt);
  if (resetsMs == null) {
    return "리셋 시각 정보 없음";
  }
  const leftMs = resetsMs - nowMs;
  if (leftMs <= 0) {
    return "리셋 시각이 지났습니다. 새로고침을 눌러 보세요";
  }
  return `리셋까지 ${durationText(leftMs)} (${dateTimeText(resetsMs)})`;
}

function durationText(ms: number): string {
  const totalMinutes = Math.max(1, Math.ceil(ms / 60_000));
  const days = Math.floor(totalMinutes / 1440);
  const hours = Math.floor((totalMinutes % 1440) / 60);
  const minutes = totalMinutes % 60;
  if (days > 0) {
    return `${days}일 ${hours}시간`;
  }
  if (hours > 0) {
    return `${hours}시간 ${minutes}분`;
  }
  return `${minutes}분`;
}

/** 이 기기의 현지 시각으로 "9월 29일 21:40"처럼 쓴다. */
export function dateTimeText(ms: number): string {
  const date = new Date(ms);
  return `${date.getMonth() + 1}월 ${date.getDate()}일 ${timeText(ms)}`;
}

export function timeText(ms: number): string {
  const date = new Date(ms);
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function sameLocalDay(leftMs: number, rightMs: number): boolean {
  const left = new Date(leftMs);
  const right = new Date(rightMs);
  return (
    left.getFullYear() === right.getFullYear() &&
    left.getMonth() === right.getMonth() &&
    left.getDate() === right.getDate()
  );
}

/** Claude 리셋 시각은 소수점 아래 여섯 자리로 온다. 어느 JS 엔진에서도 읽히게 밀리초까지만 남긴다. */
export function parseTime(value: string | null | undefined): number | null {
  if (value == null) {
    return null;
  }
  const ms = Date.parse(value.replace(/(\.\d{3})\d+/, "$1"));
  return Number.isNaN(ms) ? null : ms;
}

export function numberText(value: number): string {
  return String(Math.round(value)).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}
