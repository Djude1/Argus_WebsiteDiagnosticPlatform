#!/usr/bin/env pwsh
# Node 22 portable build helper.
# System Node v24 + Rollup 4.x on Windows triggers STATUS_STACK_BUFFER_OVERRUN,
# so we pin builds to a portable Node 22 install. Update $node22 if the path moves.
# Usage: from the `frontend` folder, run `.\build-node22.ps1`.
# (Pure ASCII to avoid PowerShell 5.1 cp950 read errors on Big5 default terminals.)

$ErrorActionPreference = "Stop"

# Try known Node 22 locations in order. First hit wins.
$candidates = @("D:\nodejs", "D:\node22", "D:\Node")
$node22 = $null
foreach ($p in $candidates) {
    if (Test-Path "$p\node.exe") { $node22 = $p; break }
}

if (-not $node22) {
    Write-Error "No portable Node 22 found in: $($candidates -join ', '). Install Node 22 in one of those paths."
    exit 1
}

$env:PATH = "$node22;" + $env:PATH
Write-Host "Using Node $(& "$node22\node.exe" --version) at $node22"
& "$node22\npm.cmd" run build
exit $LASTEXITCODE
