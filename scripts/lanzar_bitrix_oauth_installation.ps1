[CmdletBinding()]
param(
    [switch]$OpenPortal
)

$ErrorActionPreference = "Stop"
$projectRoot = [System.IO.Path]::GetFullPath(
    (Split-Path -Parent $PSScriptRoot)
)
$runtimeRoot = Join-Path $projectRoot ".oauth-install-runtime"
$runName = [Guid]::NewGuid().ToString("N")
$runDirectory = Join-Path $runtimeRoot $runName
$serverOut = Join-Path $runDirectory "server.out.log"
$serverErr = Join-Path $runDirectory "server.err.log"
$tunnelLog = Join-Path $runDirectory "cloudflared.log"
$readyPath = Join-Path $runDirectory "ready.json"
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$envPath = Join-Path $projectRoot ".env"
$cloudflaredPath = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$chromePath = "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
$portalUrl = "https://viaindustrial.bitrix24.es/"
$localPort = 8765
$localBaseUrl = "http://127.0.0.1:$localPort"
$callbackPath = "/bitrix-connector/installation"
$serverProcess = $null
$tunnelProcess = $null
$savedEnvironment = @{}

function Confirm-ChildPath {
    param(
        [Parameter(Mandatory)]
        [string]$Parent,
        [Parameter(Mandatory)]
        [string]$Child
    )

    $parentFull = [System.IO.Path]::GetFullPath($Parent).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar
    )
    $childFull = [System.IO.Path]::GetFullPath($Child)
    $prefix = $parentFull + [System.IO.Path]::DirectorySeparatorChar
    if (-not $childFull.StartsWith(
        $prefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "oauth_install_runtime_path_outside_project"
    }
}

function Set-PrivateRuntimeAcl {
    param(
        [Parameter(Mandatory)]
        [string]$LiteralPath
    )

    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl = [System.Security.AccessControl.DirectorySecurity]::new()
    $acl.SetAccessRuleProtection($true, $false)
    $rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
        $identity,
        [System.Security.AccessControl.FileSystemRights]::FullControl,
        [System.Security.AccessControl.InheritanceFlags]"ContainerInherit, ObjectInherit",
        [System.Security.AccessControl.PropagationFlags]::None,
        [System.Security.AccessControl.AccessControlType]::Allow
    )
    $acl.AddAccessRule($rule)
    Set-Acl -LiteralPath $LiteralPath -AclObject $acl
}

function Set-ChildEnvironment {
    $overrides = @{
        NIA_BITRIX_MODE = "off"
        NIA_BITRIX_INSTALLATION_ENABLED = "true"
        NIA_BITRIX_PILOT_ENABLED = "false"
        NIA_BITRIX_PILOT_EMERGENCY_STOP = "true"
    }
    foreach ($entry in $overrides.GetEnumerator()) {
        $savedEnvironment[$entry.Key] = [Environment]::GetEnvironmentVariable(
            $entry.Key,
            "Process"
        )
        [Environment]::SetEnvironmentVariable(
            $entry.Key,
            $entry.Value,
            "Process"
        )
    }
}

function Restore-Environment {
    foreach ($entry in $savedEnvironment.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable(
            $entry.Key,
            $entry.Value,
            "Process"
        )
    }
}

function Stop-OwnedProcess {
    param(
        [System.Diagnostics.Process]$Process
    )
    if ($null -eq $Process) {
        return
    }
    $Process.Refresh()
    if (-not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        $Process.WaitForExit(5000) | Out-Null
    }
}

Confirm-ChildPath -Parent $projectRoot -Child $runtimeRoot
Confirm-ChildPath -Parent $runtimeRoot -Child $runDirectory

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "oauth_install_python_not_found"
}
if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) {
    throw "oauth_install_env_not_found"
}
if (-not (Test-Path -LiteralPath $cloudflaredPath -PathType Leaf)) {
    throw "oauth_install_cloudflared_not_found"
}
if (Get-NetTCPConnection -State Listen -LocalPort $localPort -ErrorAction SilentlyContinue) {
    throw "oauth_install_port_in_use"
}

try {
    New-Item -ItemType Directory -Path $runDirectory -Force | Out-Null
    Set-PrivateRuntimeAcl -LiteralPath $runDirectory

    Push-Location $projectRoot
    try {
        Set-ChildEnvironment
        try {
            $serverProcess = Start-Process `
                -FilePath $pythonPath `
                -PassThru `
                -WindowStyle Hidden `
                -RedirectStandardOutput $serverOut `
                -RedirectStandardError $serverErr `
                -ArgumentList @(
                    "-m",
                    "uvicorn",
                    "bitrix_connector.installation_entrypoint:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "$localPort",
                    "--env-file",
                    $envPath,
                    "--no-access-log",
                    "--log-level",
                    "warning"
                )
        }
        finally {
            Restore-Environment
        }

        $localDeadline = [DateTimeOffset]::UtcNow.AddSeconds(25)
        $localState = $null
        while ($null -eq $localState) {
            $serverProcess.Refresh()
            if ($serverProcess.HasExited) {
                throw "oauth_install_server_stopped_before_ready_$($serverProcess.ExitCode)"
            }
            if ([DateTimeOffset]::UtcNow -ge $localDeadline) {
                throw "oauth_install_server_ready_timeout"
            }
            try {
                $localState = Invoke-RestMethod `
                    -Method Get `
                    -Uri "$localBaseUrl/healthz" `
                    -TimeoutSec 2
            }
            catch {
                Start-Sleep -Milliseconds 200
            }
        }
        if (
            $localState.effective_mode -ne "off" -or
            -not $localState.activation_locked -or
            $localState.external_calls_enabled -or
            -not $localState.installation_enabled -or
            $localState.pilot_enabled -or
            -not $localState.pilot_emergency_stop
        ) {
            throw "oauth_install_local_safety_state_invalid"
        }

        $tunnelProcess = Start-Process `
            -FilePath $cloudflaredPath `
            -PassThru `
            -WindowStyle Hidden `
            -ArgumentList @(
                "tunnel",
                "--url",
                $localBaseUrl,
                "--no-autoupdate",
                "--logfile",
                $tunnelLog,
                "--loglevel",
                "info"
            )

        $tunnelDeadline = [DateTimeOffset]::UtcNow.AddSeconds(40)
        $publicBaseUrl = $null
        while ($null -eq $publicBaseUrl) {
            $tunnelProcess.Refresh()
            if ($tunnelProcess.HasExited) {
                throw "oauth_install_tunnel_stopped_before_ready_$($tunnelProcess.ExitCode)"
            }
            if ([DateTimeOffset]::UtcNow -ge $tunnelDeadline) {
                throw "oauth_install_tunnel_ready_timeout"
            }
            if (Test-Path -LiteralPath $tunnelLog -PathType Leaf) {
                $match = Select-String `
                    -LiteralPath $tunnelLog `
                    -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" |
                    Select-Object -Last 1
                if ($null -ne $match) {
                    $publicBaseUrl = $match.Matches[0].Value
                }
            }
            if ($null -eq $publicBaseUrl) {
                Start-Sleep -Milliseconds 250
            }
        }

        $publicState = Invoke-RestMethod `
            -Method Get `
            -Uri "$publicBaseUrl/healthz" `
            -TimeoutSec 15
        if (
            $publicState.effective_mode -ne "off" -or
            -not $publicState.activation_locked -or
            $publicState.external_calls_enabled -or
            -not $publicState.installation_enabled
        ) {
            throw "oauth_install_public_safety_state_invalid"
        }

        $callbackUrl = "$publicBaseUrl$callbackPath"
        @{
            public_base_url = $publicBaseUrl
            callback_url = $callbackUrl
            effective_mode = $publicState.effective_mode
            activation_locked = $publicState.activation_locked
            external_calls_enabled = $publicState.external_calls_enabled
            installation_enabled = $publicState.installation_enabled
        } | ConvertTo-Json | Set-Content -LiteralPath $readyPath -Encoding utf8
        Set-Clipboard -Value $callbackUrl

        Write-Host ""
        Write-Host "CALLBACK HTTPS LISTO Y COPIADO AL PORTAPAPELES:" -ForegroundColor Green
        Write-Host $callbackUrl -ForegroundColor Cyan
        Write-Host ""
        Write-Host "Modo real: off | locked: true | llamadas externas del conector: false"
        Write-Warning "No cierres esta ventana hasta confirmar que Bitrix instaló la aplicación."

        if ($OpenPortal) {
            if (-not (Test-Path -LiteralPath $chromePath -PathType Leaf)) {
                throw "oauth_install_chrome_not_found"
            }
            Start-Process `
                -FilePath $chromePath `
                -ArgumentList @("--new-window", $portalUrl) |
                Out-Null
        }

        Read-Host "Cuando Codex confirme la instalación, presiona ENTER para cerrar el túnel" |
            Out-Null
    }
    finally {
        Pop-Location
    }
}
finally {
    Restore-Environment
    Stop-OwnedProcess -Process $tunnelProcess
    Stop-OwnedProcess -Process $serverProcess
    if (Test-Path -LiteralPath $runDirectory) {
        Confirm-ChildPath -Parent $runtimeRoot -Child $runDirectory
        Remove-Item -LiteralPath $runDirectory -Recurse -Force
    }
    if (
        (Test-Path -LiteralPath $runtimeRoot) -and
        -not (Get-ChildItem -LiteralPath $runtimeRoot -Force)
    ) {
        Confirm-ChildPath -Parent $projectRoot -Child $runtimeRoot
        Remove-Item -LiteralPath $runtimeRoot -Force
    }
}
