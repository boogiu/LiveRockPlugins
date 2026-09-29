# 개발·테스트 환경 분리

평소 쓰는 개발 환경(DEV)을 그대로 둔 채, 개발 중인 플러그인 **하나만** 올라간 에이전트를 같은
Paseo 앱에서 나란히 띄워 시험하는 방법이다. DEV에 설치된 플러그인(이름이 겹치는 스킬 포함)은
테스트 에이전트에 섞이지 않고, 저장소의 파일을 고치면 재설치 없이 다음 테스트 에이전트에 반영된다.

설정 폴더·환경변수·연결 폴더가 각각 어떤 원리로 이 분리를 만드는지는 [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md)에
처음 보는 사람 기준으로 풀어 두었다.

## 구조

- **DEV**: 평소의 `~/.claude`, `~/.codex`, `~/.paseo`. 개발 보조 플러그인이 설치돼 있다.
- **클린 설정**: `~/agent-clean/claude`(Claude `CLAUDE_CONFIG_DIR`), `~/agent-clean/codex`(Codex `CODEX_HOME`).
  인증·설치 플러그인·settings가 DEV와 완전히 분리된다.
- **시험 대상 연결 폴더**: `~/agent-clean/under-test`. 시험할 저장소(worktree) 루트를 가리키는 연결 폴더(junction)다.
  테스트 provider는 항상 이 경로를 보므로, 다른 worktree를 시험할 때는 설정이 아니라 연결만 바꾼다.
- **테스트 provider**: Paseo 설정 `agents.providers`에 추가하는 항목. 기본 provider를 `extends`하고,
  `command`로 연결 폴더 안의 플러그인 경로를, `env`로 클린 설정 경로를 넘긴다.
- **CLEAN 데몬(선택)**: `~/paseo-clean`을 홈으로 쓰는 두 번째 Paseo 데몬(127.0.0.1:6800).
  Paseo 쪽 설정까지 분리해야 할 때만 쓴다(아래 "격리 범위").

## 셋업

pwsh 7에서 저장소 루트 기준으로 실행한다.

```powershell
pwsh tools/test-env/setup.ps1
```

스크립트는 클린 디렉터리와 연결 폴더를 만들고, CLEAN 데몬 설정(`~/paseo-clean/config.json`)에 테스트
provider를 병합하고, DEV 데몬에 넣을 `agents` 블록을 출력한다. DEV 파일은 고치지 않는다. 옵션:
`-Target`(시험할 저장소 루트. 생략하면 현재 연결을 유지하고, 연결이 없으면 스크립트가 있는 저장소),
`-PluginName`(생략하면 `plugins/` 아래 하나뿐인 폴더), `-CleanRoot`(기본 `~/agent-clean`),
`-PaseoCleanHome`(기본 `~/paseo-clean`), `-Port`(기본 6800), `-SyncCodex`(아래 Codex 절).

이어서 한 번만 할 일:

1. **클린 Claude 로그인**

   ```powershell
   $env:CLAUDE_CONFIG_DIR = "$HOME\agent-clean\claude"; claude   # /login 후 /exit
   ```

   `~/agent-clean/claude/.credentials.json`이 생기면 끝이다.

2. **DEV 데몬에 provider 추가**: 스크립트가 출력한 `agents` 블록을 `~/.paseo/config.json`
   최상위에 병합한다(이미 `agents.providers`가 있으면 항목만 추가하거나 같은 이름 항목을 바꾼다).
   경로가 연결 폴더로 고정이라 시험 대상을 바꿔도 다시 할 필요가 없다. 그다음:

   ```powershell
   paseo daemon reload
   paseo provider ls        # claude-liverock-toolkit-test 가 available 이어야 한다
   ```

3. **(선택) CLEAN 데몬 시작**: PowerShell에서 `paseo daemon start --home ~/paseo-clean`.
   이미 떠 있으면 `paseo daemon reload --host 127.0.0.1:6800`.

## 사용

- **테스트**: Paseo 앱에서 에이전트를 만들 때 provider로 `Claude (liverock-toolkit test)`를 고른다.
  CLI로는 `paseo run --provider claude-liverock-toolkit-test --cwd <시험할 프로젝트> "<프롬프트>"`.
- **개발**: 평소처럼 기본 `claude` provider를 쓴다. 두 에이전트는 동시에 돌아도 서로 영향이 없다.
- **수정 반영**: 연결된 저장소의 파일을 고친 뒤 **새** 테스트 에이전트를 띄운다. 재설치·reload는 필요 없다.
  이미 실행 중인 에이전트에는 반영되지 않는다.
- **다른 worktree 시험**: `pwsh tools/test-env/setup.ps1 -Target <worktree 경로>`로 연결을 바꾼 뒤 새 에이전트를
  띄운다. 한 번에 하나의 worktree만 시험된다. 지금 무엇이 연결돼 있는지는
  `(Get-Item ~/agent-clean/under-test).Target`으로 본다.
- **확인**: 테스트 에이전트에게 "로드된 plugin과 skill 목록을 이름만 전부 출력해"를 시켜
  개발 중인 플러그인의 스킬만 보이고 DEV 플러그인이 없는지 본다.

**스킬로 실행**: 이 저장소에서 Claude Code나 Codex를 열고 "`<스킬>` 스킬로 테스트 환경에서 실행해봐"라고 하면
개발 전용 스킬 `plugin-test-env`(`.claude/skills/`, `.agents/skills/`에 같은 본문)가 위 절차를 대신 한다 —
수정본 worktree 연결, 테스트 에이전트 실행, 판정·보고·정리. 직접 부를 때는 Claude `/plugin-test-env`,
Codex `$plugin-test-env`. 두 사본은 같은 내용을 유지한다.

Paseo 없이 Claude만 확인할 때:

```powershell
$env:CLAUDE_CONFIG_DIR = "$HOME\agent-clean\claude"
claude --plugin-dir <저장소>\plugins\liverock-toolkit -p "로드된 plugin과 skill 목록을 이름만 전부 출력해"
```

## Codex

Codex에는 `--plugin-dir`에 해당하는 옵션이 없어서, 클린 `CODEX_HOME`에 연결 폴더의 마켓플레이스를
등록하고 플러그인을 설치한다. 설치본은 `~/agent-clean/codex/plugins/cache/` 아래 **복사본**이다.
Codex는 등록할 때 연결 폴더를 실제 경로로 풀어 기록하므로, `-SyncCodex`는 매번 마켓플레이스를 다시 등록한다.

1. 클린 Codex 로그인(한 번만): `$env:CODEX_HOME = "$HOME\agent-clean\codex"; codex login`
   (폴더가 없으면 로그인이 실패하므로 `setup.ps1`을 먼저 실행한다.)
2. 설치: `pwsh tools/test-env/setup.ps1 -SyncCodex`
3. 테스트: provider `Codex (liverock-toolkit test)`(`codex-liverock-toolkit-test`)로 에이전트를 띄운다.
   Paseo 없이 확인할 때:

   ```powershell
   $env:CODEX_HOME = "$HOME\agent-clean\codex"
   codex exec -s read-only --ephemeral "사용 가능한 plugin과 skill 목록을 이름만 전부 출력해"
   ```

**수정 반영**: 저장소 파일을 고치거나 `-Target`을 바꾼 뒤 `pwsh tools/test-env/setup.ps1 -SyncCodex`를 다시
실행하고 새 에이전트를 띄운다. 버전 문자열이 같아도 `codex plugin add`가 캐시를 덮어쓴다.
`marketplace add` 재실행이나 `marketplace upgrade`(Git 마켓플레이스 전용)로는 반영되지 않는다.

## 격리 범위

테스트 provider로 띄운 에이전트에서 분리되는 것과 공유되는 것:

- 분리: Claude/Codex의 설치 플러그인·스킬·인증·settings.
- 공유(DEV 데몬에 추가한 경우): Paseo의 `appendSystemPrompt`, 에이전트 프로필, 설치된 Paseo 플러그인,
  Paseo MCP 주입, 워크스페이스 목록.

공유 항목까지 빼고 봐야 하면 같은 provider를 CLEAN 데몬에서 쓴다. Paseo 플러그인(데몬 단위 설치)을
개발할 때도 CLEAN 데몬에만 설치한다.

## 주의

- **계정 단위 스킬**: 클린 설정에도 Claude 계정에 붙은 `anthropic-skills`와 내장 스킬은 보인다.
  DEV와의 차이가 아니므로 판정에서 뺀다.
- **Codex 사용자 공용 스킬**: `~/.agents/skills/`의 스킬은 `CODEX_HOME`을 바꿔도 클린 Codex에 함께
  로드된다. DEV 유출로 오인하지 않도록 판정 전에 그 목록을 확인한다.
- **클린 Claude 설정에 같은 플러그인을 설치하지 않는다**: `claude plugin install`로 설치하면 캐시에
  복사본이 생겨 `--plugin-dir`과 두 벌로 로드된다. 이미 설치했다면
  `claude plugin disable <플러그인>@<마켓플레이스>`(클린 `CLAUDE_CONFIG_DIR` 설정 상태에서)로 끈다.
- **데몬 PATH**: 데몬은 시작한 셸의 PATH를 물려받는다. Git Bash 같은 축소된 셸에서 시작하면
  `claude`/`codex`를 못 찾는다(`paseo daemon status`의 Providers가 `not found`). PowerShell에서 시작한다.
- **에이전트 안에서 `paseo run`**: Paseo 에이전트 셸에는 `PASEO_AGENT_ID`, `PASEO_AGENT_CWD`, `PASEO_HOME`이
  들어 있다. 이 상태로 `paseo run`을 부르면 호출자 에이전트의 하위 실행이 되어 `--cwd`가 무시되고
  호출자의 워크스페이스(보통 개발 저장소)에서 뜬다. 앞의 두 변수를 지운 프로세스에서 실행하고
  `paseo agent inspect <id>`로 Cwd를 확인한다. CLEAN 데몬에 보낼 때는 `PASEO_HOME`도 지우고
  `--host 127.0.0.1:6800`을 명시한다. `paseo daemon reload`는 `--home`이 아니라 `--host`를 받는다.
- **연결 폴더는 공용**: DEV와 CLEAN 데몬의 테스트 provider가 같은 연결 폴더를 본다. `-Target`을 바꾸면 양쪽의
  시험 대상이 함께 바뀐다. 연결 폴더를 지울 때는 `[System.IO.Directory]::Delete(<경로>)`처럼 연결만 지운다
  (재귀 삭제는 대상 저장소의 내용까지 지울 수 있다).
- **CLEAN 데몬 상태 확인**: `paseo daemon status --home ~/paseo-clean`을 쓴다. `--host`를 붙인 status는
  DEV 데몬 정보를 보여 줄 수 있다.
- **버전**: npm CLI로 띄운 CLEAN 데몬과 Paseo 데스크톱 앱이 관리하는 DEV 데몬은 버전이 다를 수 있다.
  `paseo daemon status`로 둘의 Daemon Version을 비교한다.
