"""한 실행의 워커별 토큰 사용량을 합산해 표로 낸다. 완료 보고(00_요약.md)의 「진행 과정」에 싣는다.

`paseo inspect`는 마지막 한 번의 사용량(LastUsage)만 주므로, 워커 전체 합계는 각 provider가
남긴 세션 기록에서 센다.

사용:
    python run_usage.py <실행 디렉터리의 GRAPH.md>      GRAPH.md의 agentId 열을 읽는다
    python run_usage.py --agent <agentId> [...]          agentId를 직접 준다

읽는 위치(환경 변수가 있으면 그쪽):
    Paseo 에이전트 기록   $PASEO_HOME/agents/*/<agentId>.json   (기본 ~/.paseo)
    codex 세션            $CODEX_HOME/sessions, archived_sessions (기본 ~/.codex)
    Claude 세션           $CLAUDE_CONFIG_DIR/projects             (기본 ~/.claude)

합계의 대부분은 캐시된 입력이다. 캐시도 요금제 한도를 쓰므로 함께 센다.
기록을 못 찾은 워커는 "기록 없음"으로 표시하고, 예외로 멈추지 않는다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HOME = Path.home()
PASEO = Path(os.environ.get("PASEO_HOME", HOME / ".paseo"))
CODEX = Path(os.environ.get("CODEX_HOME", HOME / ".codex"))
CLAUDE = Path(os.environ.get("CLAUDE_CONFIG_DIR", HOME / ".claude"))
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def agents_from_graph(graph: Path) -> list[tuple[str, str]]:
    found = []
    for line in graph.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or not cells[0] or cells[0] in ("노드 ID", "---"):
            continue
        ids = UUID.findall(cells[-1])
        if ids:
            found.append((cells[0], ids[0]))
    return found


def agent_record(agent_id: str) -> dict | None:
    for path in (PASEO / "agents").glob(f"*/{agent_id}.json"):
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def codex_usage(session_id: str) -> dict | None:
    files = list((CODEX / "sessions").rglob(f"*{session_id}.jsonl")) + list(
        (CODEX / "archived_sessions").glob(f"*{session_id}.jsonl")
    )
    if not files:
        return None
    last = None
    with files[0].open(encoding="utf-8") as handle:
        for line in handle:
            if '"token_count"' not in line:
                continue
            payload = json.loads(line).get("payload") or {}
            if payload.get("type") == "token_count" and payload.get("info"):
                last = payload["info"].get("total_token_usage")
    if not last:
        return None
    return {
        "total": last.get("total_tokens", 0),
        "cached": last.get("cached_input_tokens", 0),
        "output": last.get("output_tokens", 0),
    }


def claude_usage(session_id: str) -> dict | None:
    files = list((CLAUDE / "projects").glob(f"*/{session_id}.jsonl"))
    if not files:
        return None
    seen: set[str] = set()
    total = cached = output = 0
    with files[0].open(encoding="utf-8") as handle:
        for line in handle:
            if '"usage"' not in line:
                continue
            entry = json.loads(line)
            message = entry.get("message") or {}
            usage = message.get("usage")
            key = f"{message.get('id')}:{entry.get('requestId')}"
            if not usage or key in seen:
                continue
            seen.add(key)
            read = usage.get("cache_read_input_tokens", 0)
            out = usage.get("output_tokens", 0)
            total += usage.get("input_tokens", 0) + read + usage.get("cache_creation_input_tokens", 0) + out
            cached += read
            output += out
    return {"total": total, "cached": cached, "output": output}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("graph", nargs="?", help="실행 디렉터리의 GRAPH.md")
    parser.add_argument("--agent", nargs="*", default=[], help="agentId를 직접 줄 때")
    args = parser.parse_args()

    targets = [(a[:8], a) for a in args.agent]
    if args.graph:
        try:
            targets += agents_from_graph(Path(args.graph))
        except OSError as error:
            print(f"[run_usage] GRAPH.md를 읽지 못함: {error}", file=sys.stderr)
    if not targets:
        print("[run_usage] agentId를 찾지 못했다 — GRAPH.md 경로나 --agent를 확인하라", file=sys.stderr)
        return 0

    print("| 노드 | provider/model | thinking | 총 토큰 | 캐시 입력 | 출력 |")
    print("| --- | --- | --- | ---: | ---: | ---: |")
    grand = 0
    for node, agent_id in targets:
        record = agent_record(agent_id) or {}
        runtime = record.get("runtimeInfo") or {}
        provider = record.get("provider") or runtime.get("provider") or "?"
        session = runtime.get("sessionId") or (record.get("persistence") or {}).get("sessionId")
        usage = None
        try:
            if session and provider == "codex":
                usage = codex_usage(session)
            elif session and provider == "claude":
                usage = claude_usage(session)
        except (OSError, ValueError) as error:
            print(f"[run_usage] {node} 기록 읽기 실패: {error}", file=sys.stderr)
        label = f"{provider}/{runtime.get('model', '?')}"
        thinking = runtime.get("thinkingOptionId", "?")
        if usage is None:
            print(f"| {node} | {label} | {thinking} | 기록 없음 | | |")
            continue
        grand += usage["total"]
        print(f"| {node} | {label} | {thinking} | {usage['total']:,} | {usage['cached']:,} | {usage['output']:,} |")
    print(f"| 합계 | | | {grand:,} | | |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
