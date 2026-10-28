# 注册 Windows 计划任务：每周二自动执行 python main.py --run
# 用法：PowerShell 里执行  .\register_task.ps1
# 改了 config.yaml 的 schedule.time/weekday 后重跑一次本脚本即可更新。

$TaskName = "LuckinAutoTuesday"
$Time     = "08:30"    # 与 config.yaml 的 schedule.time 保持一致
$Day      = "Tuesday"  # 与 schedule.weekday 保持一致（tue -> Tuesday）

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
