param(
    [ValidateSet("cli", "web", "both")]
    [string]$Mode = "both",

    [switch]$NoManageLab,

    [string[]]$PasswordList,

    [string]$GeneratedRoot = "passwords/raw",

    [string]$Pattern = "*.txt",

    [string]$BaseUrl,

    [string]$Username,

    [int]$MaxPasswords = 0,

    [double]$Delay = 0,

    [switch]$AutoResetOnBlock,

    [switch]$NoAutoResetOnBlock,

    [switch]$KeepCommentLines,

    [switch]$SkipCommentLines,

    [string]$CsvLog
)

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

$labApp = Join-Path $repoRoot "login-lab\app.py"
$attackScript = Join-Path $repoRoot "attack\main.py"
$labEnvFile = Join-Path $repoRoot "login-lab\.env"
$attackEnvFile = Join-Path $repoRoot "attack\.env"

function Get-LabEnvValue {
    param(
        [string]$Name,
        [string]$Default = ""
    )

    $envFile = $labEnvFile
    if (-not (Test-Path $envFile)) {
        return $Default
    }

    foreach ($line in Get-Content $envFile) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
            continue
        }

        $parts = $trimmed.Split("=", 2)
        $key = $parts[0].Trim()
        $value = $parts[1].Trim()

        if ($key -ne $Name) {
            continue
        }

        if ($value.Length -ge 2 -and $value[0] -eq $value[-1] -and ('"', "'") -contains $value[0]) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        return $value
    }

    return $Default
}

function Get-LabBaseUrl {
    $port = Get-LabEnvValue -Name "PORT" -Default "5000"
    return "http://127.0.0.1:$port"
}

function Get-AttackEnvValue {
    param(
        [string]$Name,
        [string]$Default = ""
    )

    $envFile = $attackEnvFile
    if (-not (Test-Path $envFile)) {
        return $Default
    }

    foreach ($line in Get-Content $envFile) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
            continue
        }

        $parts = $trimmed.Split("=", 2)
        $key = $parts[0].Trim()
        $value = $parts[1].Trim()

        if ($key -ne $Name) {
            continue
        }

        if ($value.Length -ge 2 -and $value[0] -eq $value[-1] -and ('"', "'") -contains $value[0]) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        return $value
    }

    return $Default
}

    if (-not $BaseUrl) {
        $BaseUrl = Get-AttackEnvValue -Name "ATTACK_BASE_URL"
        if (-not $BaseUrl) {
            $BaseUrl = Get-LabBaseUrl
        }
    }

    $runStamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $runLogDir = Join-Path $repoRoot "login-lab\logs\$runStamp"

function Test-LabHealth {
    param([string]$Url)

    try {
        $null = Invoke-RestMethod -Uri "$Url/health" -Method Get -TimeoutSec 2
        return $true
    }
    catch {
        return $false
    }
}

function Wait-LabHealth {
    param(
        [string]$Url,
        [int]$Attempts = 30,
        [int]$DelayMilliseconds = 500
    )

    for ($i = 0; $i -lt $Attempts; $i++) {
        if (Test-LabHealth -Url $Url) {
            return $true
        }
        Start-Sleep -Milliseconds $DelayMilliseconds
    }

    return $false
}

$labStartedByScript = $false
$labProcess = $null

if (-not $NoManageLab -and -not (Test-LabHealth -Url $BaseUrl)) {
    if (-not (Test-Path $runLogDir)) {
        New-Item -ItemType Directory -Path $runLogDir -Force | Out-Null
    }

    $labStdOut = Join-Path $runLogDir "lab_stdout.log"
    $labStdErr = Join-Path $runLogDir "lab_stderr.log"
    $labProcess = Start-Process -FilePath $pythonExe -ArgumentList @("`"$labApp`"") -WorkingDirectory $repoRoot -PassThru -WindowStyle Hidden -RedirectStandardOutput $labStdOut -RedirectStandardError $labStdErr
    $labStartedByScript = $true

    if (-not (Wait-LabHealth -Url $BaseUrl)) {
        if ($labProcess -and -not $labProcess.HasExited) {
            Stop-Process -Id $labProcess.Id -Force
        }
        throw "Login lab did not become healthy at $BaseUrl. Check login-lab/logs/lab_stdout.log and login-lab/logs/lab_stderr.log."
    }
}

$args = @(
    $attackScript
)

if ($PSBoundParameters.ContainsKey('Mode')) {
    $args += @("--mode", $Mode)
}

if ($PSBoundParameters.ContainsKey('GeneratedRoot')) {
    $args += @("--generated-root", $GeneratedRoot)
}

if ($PSBoundParameters.ContainsKey('Pattern')) {
    $args += @("--pattern", $Pattern)
}

if ($PSBoundParameters.ContainsKey('MaxPasswords')) {
    $args += @("--max-passwords", "$MaxPasswords")
}

if ($PSBoundParameters.ContainsKey('Delay')) {
    $args += @("--delay", "$Delay")
}

if ($BaseUrl) {
    $args += @("--base-url", $BaseUrl)
}

if ($PSBoundParameters.ContainsKey('Username')) {
    $args += @("--username", $Username)
}

foreach ($list in $PasswordList) {
    $args += @("--password-list", $list)
}

if ($PSBoundParameters.ContainsKey('AutoResetOnBlock')) {
    $args += "--auto-reset-on-block"
}

if ($PSBoundParameters.ContainsKey('NoAutoResetOnBlock')) {
    $args += "--no-auto-reset-on-block"
}

if ($PSBoundParameters.ContainsKey('KeepCommentLines')) {
    $args += "--keep-comment-lines"
}

if ($PSBoundParameters.ContainsKey('SkipCommentLines')) {
    $args += "--skip-comment-lines"
}

if ($PSBoundParameters.ContainsKey('CsvLog')) {
    $args += @("--csv-log", $CsvLog)
}

if (-not $PSBoundParameters.ContainsKey('CsvLog')) {
    $args += @("--log-dir", $runLogDir)
}

Push-Location $repoRoot
try {
    & $pythonExe @args
    exit $LASTEXITCODE
}
finally {
    Pop-Location

    if ($labStartedByScript -and $labProcess) {
        try {
            if (-not $labProcess.HasExited) {
                Stop-Process -Id $labProcess.Id -Force
            }
        }
        catch {
        }
    }
}