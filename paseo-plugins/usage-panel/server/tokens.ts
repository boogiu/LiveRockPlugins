import { createReadStream, existsSync } from "node:fs";
import { readdir, stat } from "node:fs/promises";
import { basename, join } from "node:path";
import { createInterface } from "node:readline";
import type { TokenAmount } from "../shared/usage";

// 이 파일은 Node 내장 모듈만 쓴다. 로그 줄은 숫자·식별 필드만 꺼내고 나머지는 그 자리에서 버린다.

export type TimeRange = {
  /** 이 시각 이후에 수정된 파일만 읽는다. 0이면 전부 읽는다. */
  sinceMs: number;
  todayStartMs: number;
  todayEndMs: number;
};

export type SessionTotal = {
  id: string;
  firstMs: number;
  lastMs: number;
  input: number;
  output: number;
  total: number;
};

export type Collected = {
  sessions: SessionTotal[];
  today: TokenAmount;
};

/** 이 프로세스가 도는 PC의 시간대로 오늘 0시~내일 0시와, 오늘을 포함한 최근 `days`일의 시작을 잡는다. */
export function localRange(now: Date, days: number): TimeRange {
  const y = now.getFullYear();
  const m = now.getMonth();
  const d = now.getDate();
  return {
    sinceMs: new Date(y, m, d - (days - 1)).getTime(),
    todayStartMs: new Date(y, m, d).getTime(),
    todayEndMs: new Date(y, m, d + 1).getTime(),
  };
}

/** codex 세션 로그는 `sessions/YYYY/MM/DD/`와 `archived_sessions/` 두 곳에 있다. 둘 다 없으면 null. */
export async function collectCodex(codexHome: string, range: TimeRange): Promise<Collected | null> {
  const roots = [join(codexHome, "sessions"), join(codexHome, "archived_sessions")];
  if (!roots.some((root) => existsSync(root))) {
    return null;
  }
  const files = new Map<string, string>();
  for (const root of roots) {
    for (const file of await listJsonl(root, range.sinceMs)) {
      files.set(basename(file), file);
    }
  }

  const today = emptyAmount();
  const sessions: SessionTotal[] = [];
  for (const [name, file] of files) {
    // total_token_usage는 세션 안의 누적값이다. 세션 합계는 마지막 누적값, 오늘 합계는 오늘 시각인 이벤트의 증분이다.
    // 같은 누적값이 연속으로 기록되면 증분이 0이 되어 저절로 한 번만 센다.
    let previous = emptyAmount();
    let firstMs = Number.NaN;
    let lastMs = Number.NaN;
    for await (const line of readLines(file)) {
      if (!line.includes('"token_count"')) {
        continue;
      }
      const record = parseLine(line);
      if (record?.type !== "event_msg" || record.payload?.type !== "token_count") {
        continue;
      }
      const usage = record.payload.info?.total_token_usage;
      if (usage == null) {
        continue;
      }
      const atMs = Date.parse(record.timestamp);
      const current = {
        input: usage.input_tokens ?? 0,
        output: usage.output_tokens ?? 0,
        total: usage.total_tokens ?? 0,
      };
      if (atMs >= range.todayStartMs && atMs < range.todayEndMs) {
        today.input += current.input - previous.input;
        today.output += current.output - previous.output;
        today.total += current.total - previous.total;
      }
      previous = current;
      if (Number.isNaN(firstMs)) {
        firstMs = atMs;
      }
      lastMs = atMs;
    }
    if (!Number.isNaN(lastMs)) {
      sessions.push({ id: name.replace(/\.jsonl$/, ""), firstMs, lastMs, ...previous });
    }
  }
  return { sessions, today };
}

/** Claude 로그는 `projects/<프로젝트>/**` 아래 jsonl이다. 한 응답이 여러 줄로 반복 기록되므로 `(message.id, requestId)`로 한 번만 센다. */
export async function collectClaude(projectsDir: string, range: TimeRange): Promise<Collected | null> {
  if (!existsSync(projectsDir)) {
    return null;
  }
  const seen = new Set<string>();
  const today = emptyAmount();
  const bySession = new Map<string, SessionTotal>();
  for (const file of await listJsonl(projectsDir, range.sinceMs)) {
    for await (const line of readLines(file)) {
      if (!line.includes('"usage"')) {
        continue;
      }
      // usage는 대화 원문과 같은 줄에 있다. 아래 필드만 꺼내고 파싱한 객체는 이 반복 밖으로 내보내지 않는다.
      const record = parseLine(line);
      const message = record?.message;
      if (record?.type !== "assistant" || message?.usage == null || message.model === "<synthetic>") {
        continue;
      }
      const key = `${message.id}\u0000${record.requestId}`;
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);

      const usage = message.usage;
      const input =
        (usage.input_tokens ?? 0) +
        (usage.cache_creation_input_tokens ?? 0) +
        (usage.cache_read_input_tokens ?? 0);
      const output = usage.output_tokens ?? 0;
      const atMs = Date.parse(record.timestamp);
      const sessionId = String(record.sessionId);

      if (atMs >= range.todayStartMs && atMs < range.todayEndMs) {
        today.input += input;
        today.output += output;
        today.total += input + output;
      }
      const session = bySession.get(sessionId);
      if (session == null) {
        bySession.set(sessionId, {
          id: sessionId,
          firstMs: atMs,
          lastMs: atMs,
          input,
          output,
          total: input + output,
        });
      } else {
        session.firstMs = Math.min(session.firstMs, atMs);
        session.lastMs = Math.max(session.lastMs, atMs);
        session.input += input;
        session.output += output;
        session.total += input + output;
      }
    }
  }
  return { sessions: [...bySession.values()], today };
}

/** 지금 쓰이는 세션 파일은 마지막 줄이 기록 도중일 수 있다. 그런 줄은 건너뛴다. */
function parseLine(line: string) {
  try {
    return JSON.parse(line);
  } catch {
    return undefined;
  }
}

function emptyAmount(): TokenAmount {
  return { input: 0, output: 0, total: 0 };
}

async function listJsonl(dir: string, sinceMs: number): Promise<string[]> {
  if (!existsSync(dir)) {
    return [];
  }
  const found: string[] = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      found.push(...(await listJsonl(path, sinceMs)));
    } else if (entry.isFile() && entry.name.endsWith(".jsonl")) {
      if ((await stat(path)).mtimeMs >= sinceMs) {
        found.push(path);
      }
    }
  }
  return found;
}

/** 한 줄이 수 MB인 파일이 있어 파일 전체를 메모리에 올리지 않고 줄 단위로 읽는다. */
function readLines(file: string) {
  return createInterface({ input: createReadStream(file, { encoding: "utf8" }), crlfDelay: Infinity });
}
