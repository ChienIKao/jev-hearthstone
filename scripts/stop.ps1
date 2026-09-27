$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $PSScriptRoot 'run.py'
$roles = @('android_app','app','reader','advisor')
$workers = Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?\.exe$' }
foreach ($role in $roles) {
    $scriptPath = Join-Path $projectRoot "$role.py"
    $scriptPattern = [regex]::Escape($scriptPath) + '(?:"|\s|$)'
    $runnerPattern = [regex]::Escape($runner) + '"?\s+' + [regex]::Escape($role) + '(?:\s|$)'
    foreach ($worker in $workers) {
        if ($worker.CommandLine -match $scriptPattern -or $worker.CommandLine -match $runnerPattern) {
            Stop-Process -Id $worker.ProcessId -ErrorAction SilentlyContinue
        }
    }
}
Write-Output 'Laya Hearthstone processes stopped.'
