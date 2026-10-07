param([string]$InputDocx, [string]$OutputPdf, [string]$MapJson)
$ErrorActionPreference = 'Stop'
$app = $null
$doc = $null
try {
    $app = New-Object -ComObject Word.Application
    $app.Visible = $false
    $app.DisplayAlerts = 0
    $app.AutomationSecurity = 3
    $doc = $app.Documents.Open($InputDocx, $false, $true, $false)
    $doc.Repaginate()
    $pageMap = @{}
    foreach ($bookmark in $doc.Bookmarks) {
        if ($bookmark.Name.StartsWith('v10b')) {
            $range = $bookmark.Range.Duplicate
            $range.Collapse(1)
            $pageMap[$bookmark.Name] = @{ page = $range.Information(1); physical = $range.Information(3) }
        }
    }
    $pageMap | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $MapJson -Encoding utf8
    $doc.ExportAsFixedFormat($OutputPdf, 17)
    Write-Output ('WORD_PDF_PAGES ' + $doc.ComputeStatistics(2))
} finally {
    if ($null -ne $doc) { $doc.Close(0); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($doc) }
    if ($null -ne $app) { $app.Quit(); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($app) }
}
