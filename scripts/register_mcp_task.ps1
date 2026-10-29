# 注册瑞幸 MCP 下单计划任务
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File register_mcp_task.ps1 [-Once]
param(
    [switch]$Once,                # -Once = 只跑一次（明早），否则每周二 08:50 常驻
    [string]$At = "2026-10-30 09:00"
)
$Root = "C:\Users\Administrator\.zcode\workspace\9af7e246-9f04-46ee-9ce9-cb285b2aad54\luckin-auto"
$Action = New-ScheduledTaskAction -Execute "$Root\scripts\run_order.cmd"
if ($Once) {
    $Trigger = New-ScheduledTaskTrigger -Once -At ([datetime]$At)
} else {
    $Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday -At 08:50
}
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 90)
Register-ScheduledTask -TaskName "LuckinMcpOrder" -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
$task = Get-ScheduledTask -TaskName "LuckinMcpOrder"
$info = Get-ScheduledTaskInfo -TaskName "LuckinMcpOrder"
Write-Host "已注册：状态 $($task.State)，下次运行 $($info.NextRunTime)"
