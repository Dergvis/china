Param(
  [Parameter(Mandatory=$true)]
  [string]$TargetDir
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$src = Join-Path $repoRoot 'miniapp'

if (-not (Test-Path $src)) {
  throw "miniapp folder not found: $src"
}

if (Test-Path $TargetDir) {
  Remove-Item -Path $TargetDir -Recurse -Force
}
New-Item -ItemType Directory -Path $TargetDir | Out-Null

Copy-Item -Path (Join-Path $src '*') -Destination $TargetDir -Recurse -Force

$required = @(
  'app.json',
  'project.config.json',
  'index.wxml',
  'index.js',
  'index.wxss'
)

$missing = @()
foreach ($rel in $required) {
  $p = Join-Path $TargetDir $rel
  if (-not (Test-Path $p)) { $missing += $rel }
}

if ($missing.Count -gt 0) {
  throw "Export failed. Missing: $($missing -join ', ')"
}

Write-Host "Miniapp exported successfully to: $TargetDir"
Write-Host "Import this exact folder in WeChat DevTools."
