# Apex System Breach Protocol Simulator v3.1415926
# FOR EDUCATIONAL/ENTERTAINMENT USE ONLY.

Function Write-HackerHost ([string]$Text, [string]$Color = "Green") {
    $Delay = Get-Random -Minimum 10 -Maximum 35
    foreach ($Char in $Text.ToCharArray()) {
        Write-Host $Char -NoNewline -ForegroundColor $Color
        Start-Sleep -Milliseconds $Delay
    }
    Write-Host ""
}

Function Update-HackerProgress ([string]$Activity, [int]$Percent, [string]$Status) {
    # 建立一個 ASCII 進度條：[=====>    ]
    $BarWidth = 30
    $CompletedWidth = [Math]::Floor(($Percent / 100) * $BarWidth)
    $RemainingWidth = $BarWidth - $CompletedWidth
    $Bar = "[" + ("=" * $CompletedWidth) + ">" + (" " * $RemainingWidth) + "]"
    
    Write-Progress -Activity "$Bar $Percent% $Activity" -Status $Status -PercentComplete $Percent
}

# --- MAIN SCRIPT ---
$host.UI.RawUI.ForegroundColor = "Green"
Clear-Host

Write-HackerHost "[+] INITIALIZING APEX PROTOCOL v3.1..."
Start-Sleep -Milliseconds 800
Write-HackerHost "[!] TARGET NETWORK IDENTIFIED: 10.10.1.254" "Yellow"
Start-Sleep -Milliseconds 600
Write-HackerHost "[!] FIREWALL LEVEL: HIGH DETECTED. INITIATING ADAPTIVE BYPASS..." "Red"
Start-Sleep -Seconds 1

# STAGE 1: DECRYPTION
$Activity1 = "DECRYPTING SHA-256 HASHES"
for ($i = 0; $i -le 100; $i += (Get-Random -Min 1 -Max 5)) {
    if ($i -gt 100) { $i = 100 }
    $Hash = (New-Guid).Guid.Substring(0, 16).ToUpper()
    Update-HackerProgress $Activity1 $i "Current Hash: 0x$Hash... [1240/1400 keys tried]"
    
    # 模擬偶爾的輸出以增加真實感
    if ($i -eq 50) { Write-HackerHost "  > Identified weak nonce pattern..." "Cyan" }
    Start-Sleep -Milliseconds (Get-Random -Min 30 -Max 120)
}
Write-HackerHost "[+] STAGE 1 COMPLETE: Primary credentials compromised." "Green"
Start-Sleep -Seconds 1

# STAGE 2: FIREWALL BYPASS
Write-Host "`n"
$Activity2 = "BYPASSING IDS SIGNATURES"
for ($i = 0; $i -le 100; $i += (Get-Random -Min 2 -Max 8)) {
    if ($i -gt 100) { $i = 100 }$Exploit = "CVE-202X-" + (Get-Random -Min 1000 -Max 9999)
    Update-HackerProgress $Activity2$i "Injecting polymorphism via $Exploit..."
    
    if ($i -eq 75) { Write-HackerHost "  > Traffic rerouted through phantom nodes." "Cyan" }
    Start-Sleep -Milliseconds (Get-Random -Min 50 -Max 200)
}
Write-HackerHost "[+] STAGE 2 COMPLETE: Internal network accessed." "Green"
Start-Sleep -Seconds 1

# STAGE 3: PAYLOAD DELIVERY
Write-Host "`n"
$Activity3 = "INJECTING PAYLOAD"
for ($i = 0; $i -le 100; $i += (Get-Random -Min 5 -Max 15)) {
    if ($i -gt 100) { $i = 100 }
    Update-HackerProgress $Activity3 $i "Uploading: ROOT_ACCESS.EXE..."
    Start-Sleep -Milliseconds (Get-Random -Min 80 -Max 300)
}
Write-HackerHost "[+] STAGE 3 COMPLETE: Persistent back-door established." "Green"
Start-Sleep -Seconds 1

# FINAL STATUS
Clear-Host
Write-Host "`n"
Write-HackerHost "#############################################" "Cyan"
Write-HackerHost "#                                           #" "Cyan"
Write-HackerHost "#       SYSTEM BREACH SUCCESSFUL            #" "Cyan"
Write-HackerHost "#                                           #" "Cyan"
Write-HackerHost "#############################################" "Cyan"
Write-HackerHost "`nTarget system 10.10.1.254 is now under your control." "White"
Write-Host "`nPS C:\Scripts\Project_Apex> " -NoNewline -ForegroundColor Green
# 腳本結束
