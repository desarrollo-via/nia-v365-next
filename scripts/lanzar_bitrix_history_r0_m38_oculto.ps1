param(
    [switch]$Execute,
    [switch]$SelfTest,
    [string]$ConfirmCode = "",
    [string]$DotenvPath = ".env"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$launchConfirmation = "LANZAR M38 R0 OCULTO UNA SOLA VEZ"
$outerConfirmation = "EJECUTAR SESION R0 PROTEGIDA UNA SOLA VEZ"
$armConfirmation = "ARMAR HISTORIAL CHAT78733 SIN ENVIAR MENSAJE"
$controlledText = "PRUEBA CONTROLADA NIA R0 614949 2026-08-03-01"
$moduleName = "bitrix_connector.bitrix_history_r0_protected_session_process_cli"
$projectRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..")
)
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$expectedDotenvPath = Join-Path $projectRoot ".env"
$tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$runId = [System.Guid]::NewGuid().ToString("N")
$runDirectory = Join-Path $tempRoot ("nia-next-m38-" + $runId)
$stdoutPath = Join-Path $runDirectory "stdout.jsonl"
$stderrPath = Join-Path $runDirectory "stderr.log"
$trimChars = [char[]]@(
    [System.IO.Path]::DirectorySeparatorChar,
    [System.IO.Path]::AltDirectorySeparatorChar
)

function Confirm-DirectChildPath {
    param(
        [Parameter(Mandatory = $true)][string]$Parent,
        [Parameter(Mandatory = $true)][string]$Child
    )

    $parentFull = [System.IO.Path]::GetFullPath($Parent).TrimEnd($trimChars)
    $childFull = [System.IO.Path]::GetFullPath($Child)
    $childParent = [System.IO.Path]::GetDirectoryName($childFull).TrimEnd($trimChars)
    if (-not [System.String]::Equals(
        $parentFull,
        $childParent,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "m38_hidden_launcher_unsafe_child_path"
    }
    return $childFull
}

function Write-PublicSnapshot {
    param(
        [Parameter(Mandatory = $true)][string]$State,
        [Parameter(Mandatory = $true)][string]$Reason,
        [bool]$RequestValid = $false,
        [bool]$ProcessStarted = $false,
        [bool]$HiddenWindow = $true,
        [bool]$ShellUsed = $false,
        [int]$LaunchAttempts = 0,
        [int]$ProcessId = 0,
        [string]$PublicRunId = "",
        [string]$FailureCategory = ""
    )

    [ordered]@{
        state = $State
        reason = $Reason
        request_valid = $RequestValid
        process_started = $ProcessStarted
        hidden_window = $HiddenWindow
        shell_used = $ShellUsed
        launch_attempts = $LaunchAttempts
        process_id = $ProcessId
        run_id = $PublicRunId
        failure_category = $FailureCategory
    } | ConvertTo-Json -Compress
}

$failureCategory = "path_guard"

function Get-Sha256Hex {
    param(
        [Parameter(Mandatory = $true)][string]$Value
    )

    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::ASCII.GetBytes($Value)
        $hashBytes = $sha256.ComputeHash($bytes)
        return [System.BitConverter]::ToString($hashBytes).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha256.Dispose()
    }
}

try {
    $runDirectory = Confirm-DirectChildPath -Parent $tempRoot -Child $runDirectory
    $stdoutPath = Confirm-DirectChildPath -Parent $runDirectory -Child $stdoutPath
    $stderrPath = Confirm-DirectChildPath -Parent $runDirectory -Child $stderrPath

    if ($SelfTest -and $Execute) {
        Write-PublicSnapshot `
            -State "REJECTED" `
            -Reason "m38_hidden_launcher_mode_rejected"
        exit 2
    }
    if ($SelfTest) {
        $failureCategory = "crypto_self_test"
        $fixtureHash = Get-Sha256Hex -Value "fixture"
        if ($fixtureHash -cne "f16d05ec6b29248d2c61adb1e9263f78e4f7bace1b955014a2d17872cfe4064d") {
            throw "m38_hidden_launcher_crypto_self_test_failed"
        }
        Write-PublicSnapshot `
            -State "READY" `
            -Reason "m38_hidden_launcher_crypto_self_test_ready" `
            -RequestValid $true
        exit 0
    }
    if (-not $Execute) {
        Write-PublicSnapshot `
            -State "PREPARED" `
            -Reason "m38_hidden_launcher_prepared" `
            -RequestValid $true
        exit 0
    }
    if ($ConfirmCode -cne $launchConfirmation) {
        Write-PublicSnapshot `
            -State "REJECTED" `
            -Reason "m38_hidden_launcher_confirmation_rejected"
        exit 2
    }
    $failureCategory = "runtime_validation"
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        throw "m38_hidden_launcher_python_not_found"
    }

    $dotenvFull = [System.IO.Path]::GetFullPath(
        (Join-Path $projectRoot $DotenvPath)
    )
    if (-not [System.String]::Equals(
        $dotenvFull,
        [System.IO.Path]::GetFullPath($expectedDotenvPath),
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "m38_hidden_launcher_dotenv_path_rejected"
    }
    if (-not (Test-Path -LiteralPath $dotenvFull -PathType Leaf)) {
        throw "m38_hidden_launcher_dotenv_not_found"
    }

    $failureCategory = "crypto_derivation"
    $expectedHash = Get-Sha256Hex -Value $controlledText
    $windowStart = [System.DateTimeOffset]::UtcNow.ToString(
        "yyyy-MM-ddTHH:mm:ss.fffffffZ"
    )

    $failureCategory = "temp_creation"
    New-Item -ItemType Directory -Path $runDirectory | Out-Null
    $arguments = @(
        "-m",
        $moduleName,
        "--confirm-code",
        ('"' + $outerConfirmation + '"'),
        "--dotenv-path",
        $dotenvFull,
        "--expected-text-sha256",
        $expectedHash,
        "--window-start-utc",
        $windowStart,
        "--arm-code",
        ('"' + $armConfirmation + '"')
    )

    $failureCategory = "process_start"
    $process = Start-Process `
        -FilePath $pythonPath `
        -ArgumentList $arguments `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -PassThru

    Write-PublicSnapshot `
        -State "STARTED" `
        -Reason "m38_hidden_launcher_started" `
        -RequestValid $true `
        -ProcessStarted $true `
        -LaunchAttempts 1 `
        -ProcessId $process.Id `
        -PublicRunId $runId
    exit 0
}
catch {
    if (Test-Path -LiteralPath $runDirectory -PathType Container) {
        Remove-Item -LiteralPath $runDirectory -Recurse -Force
    }
    Write-PublicSnapshot `
        -State "NO-GO" `
        -Reason "m38_hidden_launcher_failed_safe" `
        -RequestValid $Execute.IsPresent `
        -LaunchAttempts ([int]$Execute.IsPresent) `
        -FailureCategory $failureCategory
    exit 1
}
