$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
foreach ($role in @('reader','advisor','app')) {
    $pidFile = Join-Path $PSScriptRoot "$role.pid"
    $alive = $false
    if (Test-Path -LiteralPath $pidFile) {
        $workerId = [int](Get-Content -LiteralPath $pidFile)
        $worker = Get-CimInstance Win32_Process -Filter "ProcessId = $workerId"
        $alive = $worker -and $worker.CommandLine -like "*jev-hearthstone*$role.py*"
    }
    if (-not $alive) {
        $runArgs = @((Join-Path $PSScriptRoot "$role.py"))
        if ($role -eq 'advisor') { $runArgs += '--watch' }
        $worker = Start-Process -FilePath "$PSScriptRoot\.venv\Scripts\pythonw.exe" -ArgumentList $runArgs -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput "$PSScriptRoot\$role.log" -RedirectStandardError "$PSScriptRoot\$role-errors.log" -PassThru
        $worker.Id | Set-Content -LiteralPath $pidFile
    }
}
