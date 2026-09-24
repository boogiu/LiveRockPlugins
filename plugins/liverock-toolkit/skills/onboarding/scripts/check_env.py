#!/usr/bin/env python3
"""Paseo 데몬 없이 확인할 수 있는 온보딩 점검 항목을 한 번에 돌린다.

점검 대상은 호스트에 따라 다르다. codex에서는 로그인(10), 플러그인 설치·활성(1), Python 3(2),
네트워크(3), 실행 기록 디렉터리(8)를 본다. Claude Code에서는 codex 로그인은 해당 없으므로
건너뛰고 Claude 플러그인 설치·활성(1)과 공통 항목을 본다. Paseo 데몬에 묻는 항목(4·5·6·9)과
프로필(7)은 여기서 다루지 않는다 — 본문 2~4단계에서 `paseo` CLI로 본다.

표 아래에 provider CLI(codex·claude)의 **실제 실행 경로**를 함께 낸다. 9번(provider 실행
경로) 판정 자체는 `paseo provider ls --json`으로 하지만, 실패했을 때 사용자가 Paseo 설정에
넣을 값이 이 경로다. 못 찾았으면 어디를 찾아봤는지를 남겨 다음에 볼 자리를 알려 준다.

확인에 실패한 항목은 예외로 세션을 끊지 않고 unknown(확인 불가)으로 남긴다.
pass와 unknown은 다른 상태다 — 확인하지 못한 것을 통과로 적으면 나중에 원인을
찾을 자리가 사라진다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

PLUGIN_ID = "liverock-toolkit@liverock"
PLUGIN_NAME = "liverock-toolkit"
CLAUDE_MARKETPLACE_PARTS = (".claude-plugin", "marketplace.json")
ORCH_PARTS = (".agents", "orchestration")
OPENALEX_PROBE = "https://api.openalex.org/works?per-page=1"
PROVIDER_CLIS = ("codex", "claude")

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


def npm_global_dirs():
    """npm 전역 설치 디렉터리 후보를 환경에서 구한다. 경로를 하드코딩하지 않는다.

    npm에게 직접 묻는 것이 가장 정확하다. npm이 없거나 대답하지 않으면 사용자
    홈·APPDATA처럼 환경 변수에서 구한 기준 디렉터리로 관례 위치를 만든다.
    """
    dirs = []

    def add(path):
        if path and os.path.isdir(path) and path not in dirs:
            dirs.append(path)

    result = run(["npm", "config", "get", "prefix"], timeout=15.0)
    if result is not None and result[0] == 0:
        lines = [ln.strip() for ln in result[1].splitlines() if ln.strip()]
        if lines:
            prefix = lines[-1]
            add(prefix)
            add(os.path.join(prefix, "bin"))

    appdata = os.environ.get("APPDATA")
    if appdata:
        add(os.path.join(appdata, "npm"))

    home = os.path.expanduser("~")
    if home and home != "~":
        add(os.path.join(home, ".npm-global", "bin"))
        add(os.path.join(home, ".local", "bin"))
    return dirs


def executable_here(directory, name):
    """디렉터리 안에서 실제로 실행 가능한 파일을 고른다. 없으면 None.

    resolve()와 같은 이유로 Windows에서는 확장자가 있는 것만 고른다 — npm이 함께 까는
    확장자 없는 셸 스크립트를 잡으면 파일은 있는데 실행이 안 된다.
    """
    for candidate in (name + ".cmd", name + ".exe", name + ".bat", name):
        path = os.path.join(directory, candidate)
        if not os.path.isfile(path):
            continue
        if os.name == "nt":
            if os.path.splitext(path)[1]:
                return path
        elif os.access(path, os.X_OK):
            return path
    return None


def find_provider_cli(name, extra_dirs):
    """provider CLI 실행 파일의 실제 경로를 찾는다.

    PATH는 resolve()로 본다 — 확장자 처리가 이미 거기 있다. PATH에 없으면 흔한 설치
    디렉터리를 직접 뒤진다. 찾으면 경로를, 못 찾으면 찾아본 위치를 돌려준다.
    """
    searched = ["PATH"]
    try:
        found = resolve(name)
    except Exception as exc:  # 탐색 실패가 나머지 점검을 막지 않게 한다
        warn(name + " PATH 탐색 실패: " + repr(exc))
        found = None
    if found:
        return {"name": name, "path": found, "source": "PATH", "searched": searched}

    for directory in extra_dirs:
        searched.append(directory)
        try:
            found = executable_here(directory, name)
        except Exception as exc:
            warn(name + " " + directory + " 탐색 실패: " + repr(exc))
            continue
        if found:
            return {
                "name": name,
                "path": found,
                "source": directory,
                "searched": searched,
            }

    warn(name + " 실행 파일을 찾지 못했다. 찾아본 곳: " + ", ".join(searched))
    return {"name": name, "path": None, "source": None, "searched": searched}


def find_provider_clis():
    """9번 실패 시 사용자에게 보여 줄 provider CLI 경로를 모은다."""
    try:
        extra_dirs = npm_global_dirs()
    except Exception as exc:  # 후보 수집이 실패해도 PATH 탐색은 한다
        warn("npm 전역 디렉터리 수집 실패: " + repr(exc))
        extra_dirs = []
    return [find_provider_cli(name, extra_dirs) for name in PROVIDER_CLIS]


def render_providers(providers):
    """표 아래에 붙는 provider CLI 경로 절."""
    width = max(len(p["name"]) for p in providers)
    out = ["", "provider CLI 실행 경로"]
    for p in providers:
        head = "  " + p["name"].ljust(width) + " : "
        if p["path"]:
            out.append(head + p["path"] + "  (" + p["source"] + ")")
        else:
            out.append(head + "찾지 못함. 찾아본 곳 — " + ", ".join(p["searched"]))
    return "\n".join(out)


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


def check_login():
    """10. codex 로그인 — `codex login status`의 출력 문자열로 판정한다.

    **종료코드로 가르지 않는다.** 실측에서 로그인 여부와 무관하게 둘 다 0이었다 —
    로그인된 상태의 `Logged in using ChatGPT`도 0, 안 된 상태의 `Not logged in`도 0이다.
    종료코드로 판정하면 로그인이 안 된 환경까지 통과로 나온다.

    `Not logged in`이 `logged in`을 부분 문자열로 품으므로 부정 쪽을 먼저 본다.
    둘 다 아닌 출력이면 확인 불가다 — 모르는 출력을 통과로 적지 않는다.

    로그인은 자격 증명이고 브라우저 상호작용이 필요하므로 에이전트가 하지 않는다.
    """
    result = run(["codex", "login", "status"])
    if result is None:
        return {
            "status": UNKNOWN,
            "detail": "codex CLI를 실행하지 못했다",
            "fix": "codex CLI가 설치돼 있고 PATH에 있는지 확인한다",
        }
    _code, out, err = result
    lines = [ln.strip() for ln in out.splitlines() + err.splitlines() if ln.strip()]

    def decisive(needle):
        """판정을 가른 줄을 그대로 돌려준다. 없으면 None.

        경고 같은 다른 줄이 섞여 나올 수 있으므로 첫 줄을 근거로 쓰지 않는다.
        사용자가 보는 근거와 판정 근거가 같아야 한다.
        """
        for ln in lines:
            if needle in ln.lower():
                return ln
        return None

    hit = decisive("not logged in")
    if hit is not None:
        return {
            "status": FAIL,
            "detail": hit,
            "fix": "사용자가 codex login으로 로그인한다. 에이전트는 로그인하지 않는다",
        }
    hit = decisive("logged in")
    if hit is not None:
        return {"status": PASS, "detail": hit, "fix": ""}
    return {
        "status": UNKNOWN,
        "detail": "codex login status 출력을 해석하지 못했다: " + (lines[0] if lines else "출력 없음"),
        "fix": "출력을 그대로 사용자에게 전하고 로그인 상태를 직접 확인하게 한다",
    }


def claude_marketplace_name(repo_root):
    """저장소의 Claude Code marketplace 매니페스트에서 이름을 읽는다."""
    if repo_root is None:
        return None
    path = os.path.join(repo_root, *CLAUDE_MARKETPLACE_PARTS)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as source:
            value = json.load(source)
    except (OSError, ValueError) as exc:
        warn("Claude marketplace 매니페스트를 읽지 못했다: " + repr(exc))
        return None
    name = value.get("name") if isinstance(value, dict) else None
    if isinstance(name, str) and name.strip():
        return name.strip()
    warn("Claude marketplace 매니페스트에 name이 없다")
    return None


def claude_install_fix(repo_root):
    """검증된 marketplace 이름이 있을 때만 Claude 설치 명령을 만든다."""
    marketplace = claude_marketplace_name(repo_root)
    if marketplace:
        return "claude plugin install " + PLUGIN_NAME + "@" + marketplace + "를 실행한다"
    return "저장소 루트에서 claude --plugin-dir ./plugins/liverock-toolkit 로 로컬 플러그인을 직접 로드한다"


def claude_plugin_block(lines, start):
    """Claude plugin list에서 식별자 다음의 같은 플러그인 블록을 돌려준다."""
    block = [lines[start].strip()]
    for raw in lines[start + 1:]:
        # 다음 최상위 `plugin@marketplace` 행부터는 다른 플러그인 블록이다.
        if raw == raw.lstrip() and "@" in raw:
            break
        block.append(raw.strip())
    return block


def check_plugin(host, repo_root=None):
    """1. 호스트별 plugin list에서 liverock-toolkit 설치·활성을 본다."""
    cli = host
    result = run([cli, "plugin", "list"])
    if result is None:
        return {
            "status": UNKNOWN,
            "detail": cli + " CLI를 실행하지 못했다",
            "fix": cli + " CLI가 설치돼 있고 PATH에 있는지 확인한다",
        }
    code, out, err = result
    if code != 0:
        first = (err.strip().splitlines() or ["출력 없음"])[0]
        return {
            "status": UNKNOWN,
            "detail": cli + " plugin list 종료코드 " + str(code),
            "fix": first,
        }
    lines = out.splitlines()
    if host == "codex":
        line = next((raw.strip() for raw in lines if re.search(
            r"(?<![A-Za-z0-9_.@-])" + re.escape(PLUGIN_ID) + r"(?![A-Za-z0-9_.@-])", raw
        )), None)
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

    identifier = None
    block = None
    pattern = re.compile(r"(?<![A-Za-z0-9_.-])(" + re.escape(PLUGIN_NAME) + r"@[A-Za-z0-9_.-]+)(?![A-Za-z0-9_.-])")
    for index, raw in enumerate(lines):
        match = pattern.search(raw)
        if match:
            identifier = match.group(1)
            block = claude_plugin_block(lines, index)
            break
    if block is None:
        return {
            "status": FAIL,
            "detail": PLUGIN_NAME + "이(가) 목록에 없다",
            "fix": claude_install_fix(repo_root),
        }

    status_line = next((line for line in block if line.lower().startswith("status:")), None)
    if status_line is None:
        return {
            "status": UNKNOWN,
            "detail": identifier + "의 Status를 읽지 못했다",
            "fix": "claude plugin list 출력을 사용자에게 전하고 설치·활성 상태를 직접 확인한다",
        }
    status = status_line.partition(":")[2].lower()
    status = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", status)
    status_tokens = re.findall(r"[a-z]+", status)
    if status_tokens == ["enabled"]:
        return {"status": PASS, "detail": identifier + " / " + status_line, "fix": ""}
    if status_tokens == ["disabled"]:
        fix = "claude plugin enable " + identifier + "를 실행한다"
    else:
        fix = "Status 값을 해석하지 못했다. claude plugin list 출력을 사용자에게 전한다"
    return {
        "status": FAIL if status_tokens == ["disabled"] else UNKNOWN,
        "detail": identifier + " / " + status_line,
        "fix": fix,
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


def select_host(requested):
    """점검할 호스트를 고른다. Claude Code 표시는 codex 항목을 해당 없음으로 만든다."""
    if requested != "auto":
        return requested
    if os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_CODE_ENTRYPOINT"):
        return "claude"
    # 판별 단서가 없을 때는 기존 codex 실행 결과를 그대로 유지한다.
    return "codex"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "온보딩 점검 중 Paseo 데몬이 필요 없는 항목(10·1·2·3·8)을 확인하고, "
            "provider CLI(codex·claude)의 실제 실행 경로를 함께 찾는다."
        )
    )
    parser.add_argument("--json", action="store_true", help="결과를 JSON으로 출력한다")
    parser.add_argument(
        "--host",
        choices=("auto", "codex", "claude", "both"),
        default="auto",
        help="점검 호스트. 기본 auto는 Claude Code 환경을 감지하고, 그 밖에는 codex로 본다",
    )
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

    host = select_host(args.host)
    checks = []
    if host in ("codex", "both"):
        checks.extend(((10, "codex 로그인", check_login), (1, "플러그인 설치·활성", lambda: check_plugin("codex", repo_root))))
    if host in ("claude", "both"):
        checks.append((1, "Claude 플러그인 설치·활성", lambda: check_plugin("claude", repo_root)))
    checks.extend((
        (2, "Python 3", check_python),
        (3, "네트워크", lambda: check_network(args.network_timeout)),
        (8, "실행 기록 디렉터리", lambda: check_orchestration_dir(repo_root)),
    ))

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

    try:
        providers = find_provider_clis()
    except Exception as exc:  # 경로 탐색 실패가 점검 결과를 못 내게 하지 않는다
        warn("provider CLI 탐색이 예외로 끝났다: " + repr(exc))
        providers = []

    if args.json:
        payload = {
            "repo_root": repo_root,
            "host": host,
            "checks": rows,
            "provider_clis": providers,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if host == "claude":
            print("점검 호스트: claude (10번 codex 로그인은 해당 없음)")
        elif host == "both":
            print("점검 호스트: codex·claude")
        print(render_table(rows))
        if providers:
            print(render_providers(providers))

    # 확인 못 한 것과 실패한 것이 있어도 종료코드로 세션을 끊지 않는다.
    return 0


if __name__ == "__main__":
    sys.exit(main())
