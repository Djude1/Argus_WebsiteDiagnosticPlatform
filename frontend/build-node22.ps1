#!/usr/bin/env pwsh
# Node 22 portable build helper
# Node v24（系統預設）在 Windows + Rollup 4.x 會 STATUS_STACK_BUFFER_OVERRUN，
# 所以 build 一律走 D:\node22（portable，零污染系統）。
# 用法：在 frontend 資料夾執行 .\build-node22.ps1

$ErrorActionPreference = "Stop"
$node22 = "D:\node22"

if (-not (Test-Path "$node22\node.exe")) {
    Write-Error "找不到 $node22\node.exe — 請先依 CLAUDE.md 的「Node 22 portable」段落安裝。"
    exit 1
}

$env:PATH = "$node22;" + $env:PATH
Write-Host "使用 Node $(& "$node22\node.exe" --version) 進行 build"
& "$node22\npm.cmd" run build
exit $LASTEXITCODE
