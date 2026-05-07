#requires -Version 5.1
<#
.SYNOPSIS
    若 Memurai（或任意指定）Windows 服务未处于 Running，则尝试启动。

.DESCRIPTION
    适用于 Memurai Developer 版等到点自动退出后需要人工拉起的情况。
    建议由「任务计划程序」以 SYSTEM 或管理员身份每隔几分钟运行一次。

.EXAMPLE
    .\ensure-memurai-running.ps1

.EXAMPLE
    .\ensure-memurai-running.ps1 -ServiceName Memurai -LogPath "C:\notebooklm-py\runtime\memurai-watchdog.log"

.NOTES
    管理员 PowerShell 创建每 5 分钟执行一次的任务（路径请改成你的仓库路径）：
    schtasks /Create /TN "Memurai-KeepAlive" /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"C:\notebooklm-py\scripts\windows\ensure-memurai-running.ps1`"" /SC MINUTE /MO 5 /RU SYSTEM /RL HIGHEST /F
#>
param(
    [string]$ServiceName = "Memurai",
    [string]$LogPath = ""
)

$ErrorActionPreference = "Stop"

$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $svc) {
    $msg = "{0} [{1}] Service not installed or name mismatch." -f (Get-Date -Format "o"), $ServiceName
    if ($LogPath) {
        Add-Content -Path $LogPath -Value $msg -Encoding utf8
    }
    Write-Warning $msg
    exit 2
}

if ($svc.Status -eq "Running") {
    exit 0
}

$before = $svc.Status
try {
    Start-Service -Name $ServiceName -ErrorAction Stop
    $msg = "{0} [{1}] Was {2}, Start-Service succeeded." -f (Get-Date -Format "o"), $ServiceName, $before
    if ($LogPath) {
        Add-Content -Path $LogPath -Value $msg -Encoding utf8
    }
    Write-Host $msg
    exit 0
}
catch {
    $msg = "{0} [{1}] Was {2}, Start-Service failed: {3}" -f (
        (Get-Date -Format "o"),
        $ServiceName,
        $before,
        $_.Exception.Message
    )
    if ($LogPath) {
        Add-Content -Path $LogPath -Value $msg -Encoding utf8
    }
    Write-Error $msg
    exit 1
}
