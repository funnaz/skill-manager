param(
    [ValidateSet("grok", "agents", "claude", "codex", "cursor")]
    [string]$Scope = "grok"
)

$ErrorActionPreference = "Stop"
$Repo = "https://github.com/funnaz/skill-manager.git"
$Temp = Join-Path $env:TEMP ("skill-manager-install-" + [guid]::NewGuid().ToString())
$CliRoot = Split-Path $PSScriptRoot -Parent

if (Test-Path (Join-Path $CliRoot "cli.py")) {
    python -m pip install -r (Join-Path $CliRoot "requirements.txt")
    python (Join-Path $CliRoot "cli.py") install --git $Repo --scope $Scope
    Write-Host "Skill Manager installed to scope: $Scope"
    exit 0
}

git clone --depth 1 $Repo $Temp
python -m pip install -r (Join-Path $Temp "requirements.txt")
python (Join-Path $Temp "cli.py") install --git $Repo --scope $Scope
Remove-Item -Recurse -Force $Temp
Write-Host "Skill Manager installed to scope: $Scope"
