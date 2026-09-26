$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$roles = @('app','reader','advisor')
$workers = Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?\.exe$' }
foreach ($role in $roles) {
    $scriptPath = Join-Path $projectRoot "$role.py"
    $scriptPattern = [regex]::Escape($scriptPath) + '(?:"|\s|$)'
    foreach ($worker in $workers) {
        if ($worker.CommandLine -match $scriptPattern) {
            Stop-Process -Id $worker.ProcessId -ErrorAction SilentlyContinue
        }
    }
}
Write-Output 'Laya Hearthstone processes stopped.'
