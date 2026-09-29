#requires -Version 7
<#
.SYNOPSIS
  개발 중인 플러그인만 올라간 격리 테스트 환경을 만든다.

.DESCRIPTION
  - 클린 설정 디렉터리(<CleanRoot>/claude, <CleanRoot>/codex)를 만든다.
  - <CleanRoot>/under-test 연결 폴더(junction)가 시험할 저장소(worktree) 루트를 가리키게 한다.
    테스트 provider는 이 연결 폴더를 가리키므로, 시험 대상을 바꿀 때는 -Target으로 연결만 바꾼다.
  - CLEAN Paseo 데몬 홈(<PaseoCleanHome>/config.json)에 테스트 provider를 병합한다.
  - DEV 데몬(~/.paseo/config.json)에 넣을 provider 블록을 출력한다. DEV 파일은 고치지 않는다.
  - -SyncCodex: 클린 CODEX_HOME에 연결 폴더의 마켓플레이스를 등록하고 플러그인을 (재)설치한다.
    Codex는 설치본을 캐시에 복사하므로, 코드를 고치거나 -Target을 바꾼 뒤 Codex 테스트 전에 실행한다.
  여러 번 실행해도 같은 결과가 된다.
#>
param(
  # 시험할 저장소(worktree) 루트. 생략하면 연결 폴더의 현재 대상을 유지하고, 연결이 없으면 이 스크립트의 저장소로 만든다.
  [string]$Target,
  # 시험할 플러그인 이름(plugins/<이름>). 생략하면 대상 저장소의 plugins/ 아래 하나뿐인 폴더를 쓴다.
  [string]$PluginName,
  [string]$CleanRoot = (Join-Path $HOME 'agent-clean'),
  [string]$PaseoCleanHome = (Join-Path $HOME 'paseo-clean'),
  [int]$Port = 6800,
  [switch]$SyncCodex
)

$ErrorActionPreference = 'Stop'

$claudeHome = Join-Path $CleanRoot 'claude'
$codexHome = Join-Path $CleanRoot 'codex'
$underTest = Join-Path $CleanRoot 'under-test'
New-Item -ItemType Directory -Force $claudeHome, $codexHome, $PaseoCleanHome | Out-Null

# 연결 폴더: 링크만 만들고 지운다. 같은 경로에 실제 폴더가 있으면 건드리지 않고 멈춘다.
$link = Get-Item $underTest -Force -ErrorAction SilentlyContinue
if ($link -and $link.LinkType -ne 'Junction') { throw "$underTest 가 연결 폴더가 아니다. 직접 확인한다." }
if (-not $Target) {
  $Target = if ($link) { $link.Target } else { Join-Path $PSScriptRoot '..' '..' }
}
$Target = (Resolve-Path $Target).Path
if (-not (Test-Path (Join-Path $Target 'plugins'))) { throw "대상에 plugins/ 가 없다: $Target" }
if ($link -and $link.Target -ne $Target) {
  [System.IO.Directory]::Delete($underTest)   # 비재귀 삭제라 연결만 지워지고 대상 내용은 남는다
  $link = $null
}
if (-not $link) { New-Item -ItemType Junction -Path $underTest -Target $Target | Out-Null }

if (-not $PluginName) {
  $dirs = @(Get-ChildItem (Join-Path $Target 'plugins') -Directory)
  if ($dirs.Count -ne 1) { throw "plugins/ 아래 폴더가 여러 개다. -PluginName으로 지정한다: $($dirs.Name -join ', ')" }
  $PluginName = $dirs[0].Name
}
$pluginDir = Join-Path $underTest 'plugins' $PluginName
if (-not (Test-Path (Join-Path $pluginDir '.claude-plugin' 'plugin.json'))) { throw "플러그인 매니페스트가 없다: $pluginDir" }

$claudeExe = (Get-Command claude -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source
if (-not $claudeExe) { throw 'PATH에서 claude 실행 파일을 찾지 못했다.' }

$providers = [ordered]@{
  "claude-$PluginName-test" = [ordered]@{
    extends = 'claude'
    label   = "Claude ($PluginName test)"
    command = @($claudeExe, '--plugin-dir', $pluginDir)
    env     = [ordered]@{ CLAUDE_CONFIG_DIR = $claudeHome }
  }
  "codex-$PluginName-test" = [ordered]@{
    extends = 'codex'
    label   = "Codex ($PluginName test)"
    env     = [ordered]@{ CODEX_HOME = $codexHome }
  }
}

if ($SyncCodex) {
  $marketplaceName = (Get-Content (Join-Path $underTest '.agents' 'plugins' 'marketplace.json') -Raw | ConvertFrom-Json).name
  $env:CODEX_HOME = $codexHome
  # 등록된 원본 경로가 다를 수 있으므로(대상 변경, 이전 설정) 다시 등록한다
  $codexConfig = Join-Path $codexHome 'config.toml'
  if ((Test-Path $codexConfig) -and (Select-String -Path $codexConfig -SimpleMatch "[marketplaces.$marketplaceName]" -Quiet)) {
    codex plugin marketplace remove $marketplaceName
  }
  codex plugin marketplace add $underTest
  codex plugin add "$PluginName@$marketplaceName"
  if ($LASTEXITCODE -ne 0) { throw "codex plugin add 실패 (exit $LASTEXITCODE)" }
  Remove-Item Env:CODEX_HOME
}

function Write-JsonLf([string]$Path, $Object) {
  $json = ($Object | ConvertTo-Json -Depth 32) -replace "`r`n", "`n"
  [System.IO.File]::WriteAllText($Path, $json + "`n", [System.Text.UTF8Encoding]::new($false))
}

# CLEAN 데몬 설정에 병합
$cleanConfigPath = Join-Path $PaseoCleanHome 'config.json'
$cleanConfig = if (Test-Path $cleanConfigPath) {
  Get-Content $cleanConfigPath -Raw | ConvertFrom-Json -AsHashtable
} else {
  [ordered]@{ version = 1; daemon = [ordered]@{ relay = [ordered]@{ enabled = $false } } }
}
if (-not $cleanConfig.daemon) { $cleanConfig.daemon = [ordered]@{} }
$cleanConfig.daemon.listen = "127.0.0.1:$Port"
if (-not $cleanConfig.agents) { $cleanConfig.agents = [ordered]@{} }
if (-not $cleanConfig.agents.providers) { $cleanConfig.agents.providers = [ordered]@{} }
foreach ($key in $providers.Keys) { $cleanConfig.agents.providers[$key] = $providers[$key] }
Write-JsonLf $cleanConfigPath $cleanConfig

$devSnippet = [ordered]@{ agents = [ordered]@{ providers = $providers } } | ConvertTo-Json -Depth 32
$branch = git -C $Target branch --show-current 2>$null

@"
시험 대상      : $Target ($branch)
연결 폴더      : $underTest
플러그인       : $PluginName
클린 Claude 설정: $claudeHome
클린 Codex 홈   : $codexHome
CLEAN 데몬 설정 : $cleanConfigPath (listen 127.0.0.1:$Port)

다음 단계 (tools/test-env/README.md 참고)
1) 클린 설정 로그인 (한 번만)
   `$env:CLAUDE_CONFIG_DIR = '$claudeHome'; claude    # /login 후 /exit
   `$env:CODEX_HOME = '$codexHome'; codex login
   Codex 플러그인 설치·갱신: pwsh tools/test-env/setup.ps1 -SyncCodex
2) DEV 데몬에 쓰려면 ~/.paseo/config.json 최상위에 아래 agents 블록을 병합한 뒤 'paseo daemon reload'
   (이미 agents.providers가 있으면 그 안의 같은 이름 항목을 이것으로 바꾼다. 연결 폴더 경로는 고정이라 한 번만 하면 된다)
$devSnippet
3) CLEAN 데몬이 필요하면 PowerShell에서 시작한다
   paseo daemon start --home '$PaseoCleanHome'
   (이미 떠 있으면: paseo daemon reload --host 127.0.0.1:$Port)
"@
