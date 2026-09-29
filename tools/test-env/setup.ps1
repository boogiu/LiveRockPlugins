#requires -Version 7
<#
.SYNOPSIS
  개발 중인 플러그인만 올라간 격리 테스트 환경을 만든다.

.DESCRIPTION
  - 클린 설정 디렉터리(<CleanRoot>/claude, <CleanRoot>/codex)를 만든다.
  - CLEAN Paseo 데몬 홈(<PaseoCleanHome>/config.json)에 테스트 provider를 병합한다.
  - DEV 데몬(~/.paseo/config.json)에 넣을 provider 블록을 출력한다. DEV 파일은 고치지 않는다.
  - -SyncCodex: 클린 CODEX_HOME에 이 저장소 마켓플레이스를 등록하고 플러그인을 (재)설치한다.
    Codex는 설치본을 캐시에 복사하므로, 코드를 고친 뒤 Codex 테스트 전에 이 스위치로 다시 실행한다.
  여러 번 실행해도 같은 결과가 된다.
#>
param(
  [string]$MarketplaceRoot = (Join-Path $PSScriptRoot '..' '..'),
  [string]$PluginPath = (Join-Path $PSScriptRoot '..' '..' 'plugins' 'liverock-toolkit'),
  [string]$CleanRoot = (Join-Path $HOME 'agent-clean'),
  [string]$PaseoCleanHome = (Join-Path $HOME 'paseo-clean'),
  [int]$Port = 6800,
  [switch]$SyncCodex
)

$ErrorActionPreference = 'Stop'

$PluginPath = (Resolve-Path $PluginPath).Path
$manifest = Join-Path $PluginPath '.claude-plugin' 'plugin.json'
if (-not (Test-Path $manifest)) { throw "플러그인 매니페스트가 없다: $manifest" }
$pluginName = (Get-Content $manifest -Raw | ConvertFrom-Json).name

$claudeHome = Join-Path $CleanRoot 'claude'
$codexHome = Join-Path $CleanRoot 'codex'
New-Item -ItemType Directory -Force $claudeHome, $codexHome, $PaseoCleanHome | Out-Null

$claudeExe = (Get-Command claude -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source
if (-not $claudeExe) { throw 'PATH에서 claude 실행 파일을 찾지 못했다.' }

$providers = [ordered]@{
  "claude-$pluginName-test" = [ordered]@{
    extends = 'claude'
    label   = "Claude ($pluginName test)"
    command = @($claudeExe, '--plugin-dir', $PluginPath)
    env     = [ordered]@{ CLAUDE_CONFIG_DIR = $claudeHome }
  }
  "codex-$pluginName-test" = [ordered]@{
    extends = 'codex'
    label   = "Codex ($pluginName test)"
    env     = [ordered]@{ CODEX_HOME = $codexHome }
  }
}

if ($SyncCodex) {
  $MarketplaceRoot = (Resolve-Path $MarketplaceRoot).Path
  $marketplaceName = (Get-Content (Join-Path $MarketplaceRoot '.agents' 'plugins' 'marketplace.json') -Raw | ConvertFrom-Json).name
  $env:CODEX_HOME = $codexHome
  codex plugin marketplace add $MarketplaceRoot
  codex plugin add "$pluginName@$marketplaceName"
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

@"
플러그인        : $pluginName ($PluginPath)
클린 Claude 설정: $claudeHome
클린 Codex 홈   : $codexHome
CLEAN 데몬 설정 : $cleanConfigPath (listen 127.0.0.1:$Port)

다음 단계 (tools/test-env/README.md 참고)
1) 클린 설정 로그인 (한 번만)
   `$env:CLAUDE_CONFIG_DIR = '$claudeHome'; claude    # /login 후 /exit
   `$env:CODEX_HOME = '$codexHome'; codex login
   Codex 플러그인 설치·갱신: pwsh tools/test-env/setup.ps1 -SyncCodex
2) DEV 데몬에 쓰려면 ~/.paseo/config.json 최상위에 아래 agents 블록을 병합한 뒤 'paseo daemon reload'
   (이미 agents.providers가 있으면 그 안에 항목만 추가한다)
$devSnippet
3) CLEAN 데몬이 필요하면 PowerShell에서 시작한다
   paseo daemon start --home '$PaseoCleanHome'
   (이미 떠 있으면: paseo daemon reload --host 127.0.0.1:$Port)
"@
