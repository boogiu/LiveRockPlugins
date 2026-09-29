---
name: plugin-test-env
description: 이 저장소에서 개발 중인 플러그인을, DEV 플러그인이 섞이지 않은 격리 테스트 에이전트(Paseo provider claude-<플러그인>-test / codex-<플러그인>-test)로 띄워 실제 사용자처럼 시험하고 결과를 보고한다. 테스트 환경이 없으면 세팅부터 한다. "테스트 에이전트 띄워줘", "개발 중인 플러그인 테스트해봐", "고친 스킬 클린 환경에서 돌려봐", "이 스킬 발동하는지 격리해서 확인해줘", "codex에서도 테스트해줘", "테스트 환경 세팅해줘", "테스트 provider로 확인", "실사용자 환경에서 어떻게 보이는지 봐줘" 같은 요청이면 반드시 이 스킬을 쓴다. 평소 개발 에이전트(기본 claude/codex provider)로 하는 작업이나 Paseo 에이전트 프로필 검증은 이 스킬의 대상이 아니다.
---

# 개발 중 플러그인 격리 테스트

개발 에이전트(기본 `claude`/`codex` provider)는 개발 보조 플러그인이 모두 붙은 DEV 설정으로 돈다.
그 상태로 개발 중인 플러그인을 시험하면 이름이 겹치는 스킬이나 보조 플러그인의 지시가 섞여서,
실제 사용자가 보게 될 동작을 확인할 수 없다. 그래서 테스트는 클린 설정으로 뜨는 **테스트 provider**로
새 에이전트를 띄워서 한다. 구조와 셋업의 전체 설명은 저장소의 `tools/test-env/README.md`에 있다.

아래에서 `<플러그인>`은 시험할 플러그인 디렉터리 이름(`plugins/<플러그인>`)이다. 사용자가 지목하지 않았고
`plugins/` 아래가 하나뿐이면 그것을 쓴다.

## 1. 준비 상태 확인

테스트를 띄우기 전에 아래를 확인한다. 하나라도 비면 그 칸의 조치를 먼저 한다.

| 확인 | 비었을 때 |
| --- | --- |
| `paseo provider ls`에 `claude-<플러그인>-test`(Codex면 `codex-<플러그인>-test`)가 `available` | 저장소 루트에서 `pwsh tools/test-env/setup.ps1`을 실행한다. 출력된 `agents` 블록을 DEV `~/.paseo/config.json`에 병합해야 하는데, DEV 설정 변경이므로 사용자에게 블록을 보여 주고 승인받은 뒤 반영하고 `paseo daemon reload`를 실행한다 |
| `~/agent-clean/claude/.credentials.json` 존재 | 사용자에게 클린 로그인을 요청하고 기다린다: `$env:CLAUDE_CONFIG_DIR = "$HOME\agent-clean\claude"; claude` → `/login` → `/exit` |
| (Codex) `~/agent-clean/codex/auth.json` 존재 | 사용자에게 요청한다: `$env:CODEX_HOME = "$HOME\agent-clean\codex"; codex login` |

로그인은 브라우저 인증이라 에이전트가 대신할 수 없다. DEV 인증 파일을 복사해 우회하지 않는다 —
격리가 깨지고 자격 증명이 복제된다.

## 2. 시험 대상 연결

테스트 provider는 연결 폴더 `~/agent-clean/under-test`(시험할 저장소 루트를 가리키는 junction)만 본다.
사용자가 "방금 고친 것"을 기대하는데 다른 worktree가 연결돼 있으면 고치기 전 버전을 시험하고 통과로
보고하게 된다. 그래서 수정본이 어디 있는지 찾아 연결부터 맞춘다.

1. 수정 위치를 찾는다. `git worktree list`로 이 저장소의 모든 worktree를 보고, 각각 `git -C <wt> status -sb`로
   사용자가 말한 스킬·파일에 **미커밋 변경**이 있는 곳을 먼저 찾는다("방금 고친" 것은 보통 아직 커밋 전이고,
   커밋은 여러 worktree에 공통일 수 있어 구분이 안 된다). 미커밋 변경이 없으면 브랜치별 최근 커밋으로 가린다.
   한 곳으로 좁혀지지 않으면 사용자에게 묻는다.
2. 현재 연결을 `(Get-Item ~/agent-clean/under-test).Target`으로 본다. 다르면 `tools/test-env/setup.ps1`이 있는
   worktree에서 `pwsh tools/test-env/setup.ps1 -Target <수정본 worktree>`로 바꾼다(시험 대상 worktree에 스크립트가
   없어도 된다). DEV·CLEAN 데몬 설정은 이미 연결 폴더를 가리키므로 건드릴 필요가 없다. 스크립트는 실행할 때마다
   CLEAN 데몬 설정의 provider 항목을 같은 값으로 다시 쓴다. 연결은 DEV·CLEAN 양쪽이 공유하므로, 다른 사람이
   다른 대상을 시험 중일 수 있으면 바꾸기 전에 묻고, 끝나면 원래 대상으로 되돌린다.
3. **Codex**면 연결을 맞춘 뒤 같은 스크립트를 `-SyncCodex`로 한 번 더 실행한다. Codex 설치본은 캐시
   복사본이라 연결을 바꾸거나 파일을 고칠 때마다 다시 복사해야 한다. Claude는 연결 폴더를 직접 읽으므로
   할 일이 없다.

이미 떠 있는 에이전트는 시작 시점의 플러그인을 계속 쓰므로, 연결을 바꾸거나 수정할 때마다 **새** 에이전트를 띄운다.

## 3. 테스트 에이전트 실행

Paseo 에이전트 안에서 `paseo run`을 부르면 셸에 있는 `PASEO_AGENT_ID`/`PASEO_AGENT_CWD` 때문에 호출자
에이전트의 하위 실행이 되고, `--cwd`가 무시된 채 **호출자의 워크스페이스(보통 개발 저장소)**에서 뜬다.
그러면 개발 저장소의 CLAUDE.md·AGENTS.md·개발용 스킬이 섞이는데, 로드 목록만 봐서는 이 오염이 드러나지
않는다. 그래서 이 두 변수를 지운 프로세스에서 띄우고, 뜬 뒤 cwd를 확인한다.

```powershell
pwsh -NoProfile -Command {
  Remove-Item Env:PASEO_AGENT_ID, Env:PASEO_AGENT_CWD -ErrorAction SilentlyContinue
  paseo run -d --provider claude-<플러그인>-test --cwd <시험할 프로젝트> "<프롬프트>"
}
```

- `-d`를 붙여 바로 돌려받는다. 없으면 에이전트가 끝날 때까지 막히는데, 권한 대기가 생기면 끝나지 않는다.
- 출력의 `Created workspace wks_...`와 에이전트 ID를 기록한다(5절 정리에 쓴다). `-q`는 이 줄을 숨긴다.
- `paseo agent inspect <id>`의 `Cwd`가 `<시험할 프로젝트>`인지 확인한다. 다르면 그 실행은 버리고 다시 띄운다.
- 진행은 `paseo wait <id>`로 기다리고 `paseo logs <id>`로 본다. logs에는 도구 호출만 보이고 도구 출력은 없다.
  `wait`는 권한 대기에서도 돌아오므로, 돌아온 뒤 logs 끝이 대기인지 완료인지 본다.
- `<시험할 프로젝트>`: 사용자가 지정한 폴더. 없으면 `~/plugin-testproj`(없으면 빈 git 리포로 만든다).
  개발 중인 저장소 자체는 쓰지 않는다.
- `<프롬프트>`: 사용자가 실제로 쓸 법한 발화를 그대로 쓴다. 스킬 이름을 직접 부르면 발동 여부를
  시험할 수 없으므로, 발동을 보려는 시험이면 이름 없이 요청한다. `description`의 트리거를 고친 경우에는
  새로 넣은 표현 하나와 원래 있던 표현 하나를 각각 새 에이전트로 띄운다 — 새 표현이 발동하는지와
  기존 표현이 여전히 발동하는지를 함께 봐야 수정이 다른 것을 깨지 않았다고 말할 수 있다.

**테스트 에이전트가 멈췄을 때.** `bypassPermissions` 같은 우회 모드로 띄우지 않는다 — 실제 사용자 조건과 달라진다.

| 멈춘 이유 | 다음 동작 |
| --- | --- |
| 도구 권한 요청 | Paseo MCP `list_pending_permissions`(또는 `paseo agent inspect <id>`의 PendingPermissions)로 전체 요청 ID와 명령을 읽는다. `paseo permit ls`는 표·`--json` 모두 ID가 잘린다. 읽기 전용이거나 시험 목적에 필요한 것만 `respond_to_permission`(`behavior: allow`)으로 하나씩 허용한다. 실행할 스크립트는 허용 전에 읽어서 쓰기가 없는지 본다. Codex 기본 모드는 스킬 파일을 읽는 데도 승인을 요구한다 |
| 테스트 에이전트가 사용자에게 질문 | 권장·기본 선택지가 있으면 그것으로 답하고 진행한다: `respond_to_permission`에 `behavior: allow`, `updatedInput`에 원래 `questions`와 `answers: {"<질문 문장>": "<선택지 라벨>"}`. 설정을 바꾸는 선택지뿐이면 멈춘다 |
| 쓰기·삭제·외부 전송이 필요한 단계 | 허용하지 않고 멈춘다. 실사용자 환경이 아니라 이 PC에 실제로 적용되기 때문이다 |
| 허용 명령이 이 세션의 권한 규칙에 막힘 | 우회하지 않는다. 에이전트를 남겨 두고, 사용자에게 Paseo 앱에서 직접 승인할지 묻는다 |

## 4. 판정

결과를 보고하기 전에 격리가 유지됐는지부터 본다. 격리가 깨졌으면 동작 결과를 믿을 수 없다.

- **격리 확인**: 같은 방식으로 "도구를 쓰지 말고, 네 컨텍스트에 실제로 있는 plugin 이름과 skill 이름만
  나열해"를 먼저 띄운다. `<플러그인>`의 스킬이 있고 DEV 전용 플러그인이 없어야 한다. DEV 전용 플러그인은
  지금 이 세션(개발 에이전트)에 로드된 플러그인 중 `<플러그인>`이 아닌 것들이다. 3절의 cwd 확인도 격리 확인에 포함한다.
- **판정에서 빼는 것**: 클린 설정에서도 원래 그렇게 나오는 것들이다. DEV 유출이나 플러그인 결함으로 오인하지 않는다.
  - Claude: 계정 단위 `anthropic-skills:*`, 접두사 없는 내장 스킬
  - Codex: `~/.agents/skills/`의 사용자 공용 스킬, 내장 스킬(`imagegen` 등), 추천 플러그인 목록
  - 플러그인 설치 상태를 점검하는 동작의 결과: Claude 테스트 provider는 설치가 아니라 `--plugin-dir`로
    올리므로 "설치 안 됨/비활성"으로 나온다
  - DEV 데몬에서 돌렸다면 Paseo 쪽 상태(에이전트 프로필, Paseo 플러그인, 워크스페이스 목록)는 DEV 것이다.
    시험하는 스킬이 이 상태에 따라 갈라지면(예: Paseo 플러그인이 설치돼 있으면 안내를 건너뜀) DEV에서는 한쪽
    분기만 탄다. 그 분기가 사용자가 보려던 것이면 CLEAN 데몬에서 다시 돌리고, 아니면 "미확인"으로 적는다
  - 테스트 에이전트가 제시한 경로가 `~/agent-clean/under-test/...`인 것, 그리고 플러그인 폴더 밖의 저장소
    파일(연결 폴더 아래 다른 폴더)을 찾아낸 것: 연결 폴더라서 생기는 일이고, 실사용자 설치본(캐시 복사본)에는
    플러그인 폴더만 있다
- **동작 판정**: 사용자가 확인하려던 것(스킬 발동, 절차 준수, 출력 형식 등)을 로그에서 근거 줄로 짚는다.

## 5. 보고와 정리

사용자에게 항목별로 보고한다.

- provider와 에이전트 ID, cwd, 시험한 소스(연결 대상 worktree 경로·브랜치·미커밋 변경 여부)
- 보낸 프롬프트, 그리고 테스트 에이전트의 질문·권한 요청에 대신 답한 내용
- 격리 확인 결과
- 판정(통과/실패/미확인)과 근거가 된 로그 인용. 판정에서 뺀 항목은 이유와 함께 적는다
- 실패면 원인 추정과, 개발 에이전트에게 넘길 수정 포인트

끝나면 시험용 에이전트를 `paseo agent archive <id>`로 정리하고(실행 중이면 `paseo agent stop` 먼저),
이번 실행이 새로 만든 워크스페이스를 `paseo workspace archive <wks>`로 정리한다. 권한 대기로 남긴
에이전트처럼 사용자가 이어서 볼 것은 남기고, 남긴 ID와 정리 명령을 보고에 적는다.

## CLEAN 데몬을 쓸 때

Paseo 쪽 설정(프로필, `appendSystemPrompt`, Paseo 플러그인, MCP 주입)까지 DEV와 분리해야 하면 같은
provider를 CLEAN 데몬(`127.0.0.1:6800`, 홈 `~/paseo-clean`)에서 쓴다.

- 모든 `paseo` 명령에 `--host 127.0.0.1:6800`을 붙인다. 빠뜨리면 DEV 데몬에 에이전트가 생긴다.
- 3절의 두 변수에 더해 `PASEO_HOME`도 지운다. 셋 다 DEV 값이라 남겨 두면 `Caller agent ... not found`로 실패한다.
- 떠 있는지는 `paseo daemon status --home ~/paseo-clean`으로 본다(`--host`를 붙인 status는 DEV 정보를 보여 줄 수 있다).
  꺼져 있으면 PowerShell에서 `paseo daemon start --home ~/paseo-clean`으로 띄운다. Git Bash 같은
  축소된 셸에서 띄우면 PATH가 모자라 provider가 `not found`가 된다. 설정 변경 후에는
  `paseo daemon reload --host 127.0.0.1:6800`(`--home`이 아니다).
