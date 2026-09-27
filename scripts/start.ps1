param([switch]$HandsOnly, [switch]$Windows)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $PSScriptRoot 'run.py'
$runtime = Join-Path $projectRoot 'data\runtime'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$roles = if (-not $Windows) { @('android_app') } elseif ($HandsOnly) { @('reader','app') } else { @('reader','advisor','app') }
foreach ($role in $roles) {
    $pidFile = Join-Path $runtime "$role.pid"
    $alive = $false
    if (Test-Path -LiteralPath $pidFile) {
        $workerId = [int](Get-Content -LiteralPath $pidFile)
        $worker = Get-CimInstance Win32_Process -Filter "ProcessId = $workerId"
        $pattern = [regex]::Escape($runner) + '"?\s+' + [regex]::Escape($role) + '(?:\s|$)'
        $alive = $worker -and $worker.CommandLine -match $pattern
    }
    if (-not $alive) {
        $runArgs = @(('"{0}"' -f $runner), $role)
        if ($role -eq 'advisor') { $runArgs += '--watch' }
        $worker = Start-Process -FilePath "$projectRoot\.venv\Scripts\pythonw.exe" -ArgumentList $runArgs -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput "$runtime\$role.log" -RedirectStandardError "$runtime\$role-errors.log" -PassThru
        $worker.Id | Set-Content -LiteralPath $pidFile
    }
}
