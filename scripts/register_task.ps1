# 注册 Windows 计划任务：每周固定时间自动执行 python main.py --run
# 用法：PowerShell 里执行  .\register_task.ps1
# 时间和星期自动从 config.yaml 的 schedule 段读取，改完配置重跑本脚本即可更新。

$TaskName = "LuckinAutoTuesday"
$Time = "08:30"
$Day  = "Tuesday"

# 从 config.yaml 读取 schedule.time / schedule.weekday（单一配置源）
$ConfigPath = Join-Path (Split-Path -Parent $PSScriptRoot) "config.yaml"
if (Test-Path $ConfigPath) {
    $Content = Get-Content $ConfigPath -Encoding UTF8
    if ($Content -match 'time:\s*"?(\d{1,2}:\d{2})"?\s*(#.*)?$') { $Time = $Matches[1] }
    if ($Content -match 'weekday:\s*(\w{3})') {
        $Map = @{ mon = "Monday"; tue = "Tuesday"; wed = "Wednesday"
                  thu = "Thursday"; fri = "Friday"; sat = "Saturday"; sun = "Sunday" }
        $Key = $Matches[1].ToLower()
        if ($Map.ContainsKey($Key)) { $Day = $Map[$Key] }
    }
}
else {
    Write-Warning "找不到 $ConfigPath，使用默认 $Day $Time"
}

$Root = Split-Path -Parent $PSScriptRoot
$Python = (Get-Command python -ErrorAction Stop).Source

$Action  = New-ScheduledTaskAction -Execute $Python `
             -Argument "`"$Root\main.py`" --run" -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Day -At $Time
# S4U：不登录桌面也能后台运行；StartWhenAvailable：错过触发点（电脑当时关机）开机后补跑
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
              -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
              -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Principal $Principal -Settings $Settings `
    -Description "每周二早上自动点瑞幸（python main.py --run）" -Force

Write-Host ""
Write-Host "已注册计划任务 $TaskName（$Day $Time）。"
Write-Host "手动试跑一次：Start-ScheduledTask $TaskName；查看结果看 logs\run.log"
Write-Host "删除：Unregister-ScheduledTask -TaskName $TaskName"
