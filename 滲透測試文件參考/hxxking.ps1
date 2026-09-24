Clear-Host
Write-Host "[*] INITIALIZING NEURAL LINK OVERRIDE..." -ForegroundColor Cyan
Start-Sleep -Seconds 1
Write-Host "[!] FIREWALL DETECTED. INITIATING BYPASS PROTOCOL..." -ForegroundColor Yellow
Start-Sleep -Seconds 1

# 產生一個帶有動態數值的假進度條
for ($i = 1; $i -le 100; $i++) {
    $hash = (New-Guid).ToString().Substring(0,18).ToUpper()
    $status = "DECRYPTING HASH: $hash"
    Write-Progress -Activity "SYSTEM BREACH IN PROGRESS" -Status "$i% - $status" -PercentComplete $i
    Start-Sleep -Milliseconds 40
}

Clear-Host
Write-Host "[+] FIREWALL BREACHED." -ForegroundColor Green
Start-Sleep -Milliseconds 500
Write-Host "[+] ROOT ACCESS GRANTED." -ForegroundColor Green
Start-Sleep -Milliseconds 500
Write-Host "`nWelcome back, Admin." -ForegroundColor White -BackgroundColor Black
Start-Sleep -Seconds 2
