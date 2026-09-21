#!/usr/bin/env python3
"""MCP 없이 확인할 수 있는 온보딩 점검 항목을 한 번에 돌린다.

점검 대상은 네 가지다 — 플러그인 설치·활성(1), Python 3(2), 네트워크(3),
실행 기록 디렉터리(8). Paseo MCP 도구가 있어야 하는 항목(4~7)은 여기서 다루지 않는다.

확인에 실패한 항목은 예외로 세션을 끊지 않고 unknown(확인 불가)으로 남긴다.
pass와 unknown은 다른 상태다 — 확인하지 못한 것을 통과로 적으면 나중에 원인을
찾을 자리가 사라진다.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

PLUGIN_ID = "liverock-toolkit@liverock"
ORCH_PARTS = (".agents", "orchestration")
OPENALEX_PROBE = "https://api.openalex.org/works?per-page=1"

PASS = "pass"
FAIL = "fail"
UNKNOWN = "unknown"

LABEL = {PASS: "통과", FAIL: "실패", UNKNOWN: "확인 불가"}


def warn(message):
    """진단은 stdout 표를 더럽히지 않게 stderr로만 남긴다."""
    print("[check_env] " + message, file=sys.stderr)


def resolve(name):
    """실행 가능한 실제 경로를 찾는다. 없으면 None.

    npm 전역 설치는 Windows에 확장자 없는 셸 스크립트와 `.cmd`를 함께 깐다.
    `shutil.which`가 확장자 없는 쪽을 먼저 잡으면 Windows가 그것을 실행하지 못해,
    설치돼 있는데도 없는 것으로 보인다. 그래서 실행 가능한 확장자를 먼저 시도한다.
    """
    for candidate in (name + ".cmd", name + ".exe", name + ".bat", name):
        found = shutil.which(candidate)
        if found and (os.name != "nt" or os.path.splitext(found)[1]):
            return found
    return shutil.which(name)


def run(cmd, timeout=20.0):
    """외부 명령을 돌린다. 실행 자체가 불가능하면 None을 돌려 확인 불가로 넘긴다."""
    exe = resolve(cmd[0])
    if exe is None:
        warn(cmd[0] + " 실행 파일을 PATH에서 찾지 못했다")
        return None
    cmd = [exe] + list(cmd[1:])
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except Exception as exc:  # 어떤 실패든 확인 불가로 흡수한다
        warn(" ".join(cmd) + " 실행 실패: " + repr(exc))
        return None
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def find_repo_root(start):
    """.git을 가진 가장 가까운 상위 디렉터리를 저장소 루트로 본다.

    경로를 하드코딩하지 않고 실행 위치에서 거슬러 올라가 구한다.
    """
    cur = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def check_plugin():
    """1. 플러그인 설치·활성 — codex plugin list에서 installed, enabled를 본다."""
    result = run(["codex", "plugin", "list"])
    if result is None:
        return {
            "status": UNKNOWN,
            "detail": "codex CLI를 실행하지 못했다",
            "fix": "codex CLI가 설치돼 있고 PATH에 있는지 확인한다",
        }
    code, out, err = result
    if code != 0:
        first = (err.strip().splitlines() or ["출력 없음"])[0]
        return {
            "status": UNKNOWN,
            "detail": "codex plugin list 종료코드 " + str(code),
            "fix": first,
        }
    line = None
    for raw in out.splitlines():
        if PLUGIN_ID in raw:
            line = raw.strip()
            break
    if line is None:
        return {
            "status": FAIL,
            "detail": PLUGIN_ID + "이(가) 목록에 없다",
            "fix": "codex plugin add " + PLUGIN_ID,
        }
    low = line.lower()
    if "installed" in low and "enabled" in low:
        return {"status": PASS, "detail": line, "fix": ""}
    return {
        "status": FAIL,
        "detail": line,
        "fix": "installed, enabled가 아니다. codex plugin add를 다시 실행한다",
    }


def check_python():
    """2. Python 3 — scripts/의 도구들이 이 인터프리터로 돈다."""
    v = sys.version_info
    ver = "%d.%d.%d" % (v.major, v.minor, v.micro)
    if v.major >= 3:
        return {"status": PASS, "detail": "Python " + ver, "fix": ""}
    return {
        "status": FAIL,
        "detail": "Python " + ver,
        "fix": "Python 3을 설치하고 python이 그것을 가리키게 한다",
    }


def check_network(timeout):
    """3. 네트워크 — OpenAlex 공개 엔드포인트에 한 번 요청해 도달 여부만 본다.

    논문 탐색이 외부 API를 치므로 그 경로가 열려 있는지 확인하는 것이 목적이다.
    검색 결과는 쓰지 않으므로 응답 본문은 버린다.
    """
    req = urllib.request.Request(
        OPENALEX_PROBE,
        headers={"User-Agent": "liverock-onboarding-check"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            resp.read(1)
    except urllib.error.HTTPError as exc:
        # 응답이 왔다는 것 자체가 도달은 됐다는 뜻이다.
        warn("OpenAlex HTTP " + str(exc.code))
        return {
            "status": PASS,
            "detail": "OpenAlex 응답 HTTP " + str(exc.code) + " (도달함)",
            "fix": "",
        }
    except Exception as exc:  # 타임아웃·DNS·프록시 실패를 모두 흡수한다
        warn("OpenAlex 요청 실패: " + repr(exc))
        return {
            "status": FAIL,
            "detail": "OpenAlex 도달 실패: " + type(exc).__name__,
            "fix": "프록시·방화벽 설정을 확인한다. 막혀 있으면 논문 탐색이 안 된다",
        }
    return {"status": PASS, "detail": "OpenAlex 응답 HTTP " + str(code), "fix": ""}


def check_orchestration_dir(repo_root):
    """8. 실행 기록 디렉터리 — 쓸 수 있는지와 .gitignore가 덮는지를 본다.

    디렉터리를 만들지 않는다. 생성은 사용자 승인을 받고 에이전트가 하는 일이다.
    """
    if repo_root is None:
        return {
            "status": UNKNOWN,
            "detail": "저장소 루트(.git)를 찾지 못했다",
            "fix": "저장소 안에서 실행하거나 --repo-root로 경로를 준다",
        }

    rel = "/".join(ORCH_PARTS) + "/"
    target = os.path.join(repo_root, *ORCH_PARTS)
    exists = os.path.isdir(target)
    state = "있음" if exists else "없음(미생성)"

    # 없으면 만들지 않고, 실제로 존재하는 가장 가까운 상위의 쓰기 권한만 본다.
    probe = target
    while not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    writable = os.access(probe, os.W_OK | os.X_OK)

    ignored = None
    check_target = os.path.join(*(ORCH_PARTS + ("probe",)))
    result = run(["git", "-C", repo_root, "check-ignore", "-q", check_target])
    if result is not None:
        code = result[0]
        if code in (0, 1):
            ignored = code == 0
        else:
            warn("git check-ignore 종료코드 " + str(code))

    if not writable:
        return {
            "status": FAIL,
            "detail": rel + " " + state + ", 쓰기 불가",
            "fix": "저장소 디렉터리의 쓰기 권한을 확인한다",
        }
    if ignored is None:
        return {
            "status": UNKNOWN,
            "detail": rel + " " + state + ", 쓰기 가능, .gitignore 적용 여부 미확인",
            "fix": "git을 쓸 수 있는 환경에서 다시 확인한다",
        }
    if not ignored:
        return {
            "status": FAIL,
            "detail": rel + " " + state + ", 쓰기 가능, .gitignore가 덮지 않는다",
            "fix": ".gitignore에 " + rel + "를 넣을지 사용자에게 확인한다",
        }
    return {
        "status": PASS,
        "detail": rel + " " + state + ", 쓰기 가능, .gitignore 적용됨",
        "fix": "" if exists else "아직 없다. 승인 후 만든다",
    }


def render_table(rows):
    header = ("#", "항목", "결과", "내용", "다음 동작")
    body = []
    for r in rows:
        body.append((
            str(r["id"]),
            r["name"],
            LABEL[r["status"]],
            r["detail"],
            r["fix"] or "-",
        ))
    widths = []
    for i in range(len(header)):
        widths.append(max([len(header[i])] + [len(b[i]) for b in body]))

    def line(cells):
        parts = []
        for i, c in enumerate(cells):
            parts.append(c.ljust(widths[i]))
        return "| " + " | ".join(parts) + " |"

    out = [line(header), "|" + "|".join("-" * (w + 2) for w in widths) + "|"]
    for b in body:
        out.append(line(b))
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="온보딩 점검 중 MCP가 필요 없는 항목(1·2·3·8)을 확인한다."
    )
    parser.add_argument("--json", action="store_true", help="결과를 JSON으로 출력한다")
    parser.add_argument(
        "--repo-root",
        default=None,
        help="저장소 루트. 생략하면 현재 디렉터리에서 거슬러 올라가 찾는다",
    )
    parser.add_argument(
        "--network-timeout",
        type=float,
        default=5.0,
        help="네트워크 점검 타임아웃(초). 기본 5",
    )
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # 구버전 스트림이면 그대로 쓴다
            pass

    repo_root = args.repo_root or find_repo_root(os.getcwd())

    checks = (
        (1, "플러그인 설치·활성", check_plugin),
        (2, "Python 3", check_python),
        (3, "네트워크", lambda: check_network(args.network_timeout)),
        (8, "실행 기록 디렉터리", lambda: check_orchestration_dir(repo_root)),
    )

    rows = []
    for num, name, fn in checks:
        try:
            result = fn()
        except Exception as exc:  # 한 항목의 실패가 나머지를 막지 않게 한다
            warn(str(num) + "번 점검이 예외로 끝났다: " + repr(exc))
            result = {
                "status": UNKNOWN,
                "detail": "점검 중 예외: " + type(exc).__name__,
                "fix": "stderr 진단을 보고 사용자에게 알린다",
            }
        row = {"id": num, "name": name}
        row.update(result)
        rows.append(row)

    if args.json:
        payload = {"repo_root": repo_root, "checks": rows}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_table(rows))

    # 확인 못 한 것과 실패한 것이 있어도 종료코드로 세션을 끊지 않는다.
    return 0


if __name__ == "__main__":
    sys.exit(main())
