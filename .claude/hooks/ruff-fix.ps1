#requires -Version 5.1
# PostToolUse hook：Claude 寫入 Python 檔後，自動跑 ruff --fix
# 找不到 .venv\Scripts\ruff.exe 時靜默 skip（不打擾）

$ErrorActionPreference = 'SilentlyContinue'

try {
    $payload = [Console]::In.ReadToEnd() | ConvertFrom-Json
} catch {
    exit 0
}

$file = $payload.tool_input.file_path
if (-not $file) { exit 0 }
if ($file -notmatch '\.py$') { exit 0 }
if ($file -match '(migrations|__pycache__|\.venv)') { exit 0 }

# 從檔案位置往上找 .venv\Scripts\ruff.exe
$dir = Split-Path $file -Parent
while ($dir) {
    $candidate = Join-Path $dir '.venv\Scripts\ruff.exe'
    if (Test-Path $candidate) { break }
    $parent = Split-Path $dir -Parent
    if (-not $parent -or $parent -eq $dir) { exit 0 }
    $dir = $parent
}

$ruff = Join-Path $dir '.venv\Scripts\ruff.exe'
if (-not (Test-Path $ruff)) { exit 0 }

# 跑 ruff，靜默處理；exit 0 不影響 Claude 流程
& $ruff check --fix $file 2>&1 | Out-Null
exit 0
