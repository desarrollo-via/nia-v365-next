[CmdletBinding()]
param(
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"
$projectRoot = [System.IO.Path]::GetFullPath(
    (Split-Path -Parent $PSScriptRoot)
)
$runtimeRoot = Join-Path $projectRoot ".review-admin-runtime"
$runName = [Guid]::NewGuid().ToString("N")
$runDirectory = Join-Path $runtimeRoot $runName
$certificatePath = Join-Path $runDirectory "localhost-cert.pem"
$privateKeyPath = Join-Path $runDirectory "localhost-key.pem"
$readyPath = Join-Path $runDirectory "ready.signal"
$stopPath = Join-Path $runDirectory "stop.signal"
$bootstrapPath = Join-Path $runDirectory "bootstrap.secret"
$chromeProfile = Join-Path $runDirectory "chrome-profile"
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$chromePath = "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
$adminUrl = "https://localhost:8443/"
$chromeProcess = $null
$pythonProcess = $null

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
        throw "review_admin_runtime_path_outside_project"
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

function New-LocalhostCertificatePem {
    param(
        [Parameter(Mandatory)]
        [string]$CertificatePath,
        [Parameter(Mandatory)]
        [string]$PrivateKeyPath
    )

    $rsa = [System.Security.Cryptography.RSA]::Create(2048)
    try {
        $request = [System.Security.Cryptography.X509Certificates.CertificateRequest]::new(
            "CN=localhost",
            $rsa,
            [System.Security.Cryptography.HashAlgorithmName]::SHA256,
            [System.Security.Cryptography.RSASignaturePadding]::Pkcs1
        )
        $san = [System.Security.Cryptography.X509Certificates.SubjectAlternativeNameBuilder]::new()
        $san.AddDnsName("localhost")
        $san.AddIpAddress([System.Net.IPAddress]::Loopback)
        $request.CertificateExtensions.Add($san.Build())
        $request.CertificateExtensions.Add(
            [System.Security.Cryptography.X509Certificates.X509BasicConstraintsExtension]::new(
                $false,
                $false,
                0,
                $true
            )
        )
        $keyUsage = (
            [System.Security.Cryptography.X509Certificates.X509KeyUsageFlags]::DigitalSignature -bor
            [System.Security.Cryptography.X509Certificates.X509KeyUsageFlags]::KeyEncipherment
        )
        $request.CertificateExtensions.Add(
            [System.Security.Cryptography.X509Certificates.X509KeyUsageExtension]::new(
                $keyUsage,
                $true
            )
        )
        $serverAuthOids = [System.Security.Cryptography.OidCollection]::new()
        $serverAuthOids.Add(
            [System.Security.Cryptography.Oid]::new("1.3.6.1.5.5.7.3.1")
        ) | Out-Null
        $request.CertificateExtensions.Add(
            [System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension]::new(
                $serverAuthOids,
                $true
            )
        )
        $certificate = $request.CreateSelfSigned(
            [DateTimeOffset]::UtcNow.AddMinutes(-1),
            [DateTimeOffset]::UtcNow.AddHours(4)
        )
        try {
            [System.IO.File]::WriteAllText(
                $CertificatePath,
                $certificate.ExportCertificatePem()
            )
            [System.IO.File]::WriteAllText(
                $PrivateKeyPath,
                $rsa.ExportPkcs8PrivateKeyPem()
            )
            return $certificate.GetCertHashString(
                [System.Security.Cryptography.HashAlgorithmName]::SHA256
            )
        }
        finally {
            $certificate.Dispose()
        }
    }
    finally {
        $rsa.Dispose()
    }
}

function Stop-IsolatedChrome {
    param(
        [Parameter(Mandatory)]
        [string]$ProfilePath
    )

    $processes = Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe'" |
        Where-Object {
            $null -ne $_.CommandLine -and
            $_.CommandLine.IndexOf(
                $ProfilePath,
                [System.StringComparison]::OrdinalIgnoreCase
            ) -ge 0
        }
    foreach ($process in $processes) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

Confirm-ChildPath -Parent $projectRoot -Child $runtimeRoot
Confirm-ChildPath -Parent $runtimeRoot -Child $runDirectory

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "review_admin_python_not_found"
}
if (Get-NetTCPConnection -State Listen -LocalPort 8443 -ErrorAction SilentlyContinue) {
    throw "review_admin_port_8443_in_use"
}

try {
    New-Item -ItemType Directory -Path $runDirectory -Force | Out-Null
    Set-PrivateRuntimeAcl -LiteralPath $runDirectory
    $certificateFingerprint = New-LocalhostCertificatePem `
        -CertificatePath $certificatePath `
        -PrivateKeyPath $privateKeyPath

    Write-Host "Review Admin: $adminUrl"
    Write-Host "Huella SHA-256 TLS: $certificateFingerprint"
    Write-Warning "Certificado autofirmado y efímero; no se instalará confianza global."

    Push-Location $projectRoot
    try {
        $pythonProcess = Start-Process `
            -FilePath $pythonPath `
            -NoNewWindow `
            -PassThru `
            -ArgumentList @(
                "-m",
                "bitrix_connector.review_admin_local",
                "--cert-file",
                $certificatePath,
                "--key-file",
                $privateKeyPath,
                "--ready-file",
                $readyPath,
                "--stop-file",
                $stopPath,
                "--bootstrap-file",
                $bootstrapPath
            )

        $readyDeadline = [DateTimeOffset]::UtcNow.AddSeconds(25)
        while (-not (Test-Path -LiteralPath $readyPath -PathType Leaf)) {
            $pythonProcess.Refresh()
            if ($pythonProcess.HasExited) {
                throw "review_admin_server_stopped_before_ready_$($pythonProcess.ExitCode)"
            }
            if ([DateTimeOffset]::UtcNow -ge $readyDeadline) {
                throw "review_admin_server_ready_timeout"
            }
            Start-Sleep -Milliseconds 100
        }

        if (-not (Test-Path -LiteralPath $bootstrapPath -PathType Leaf)) {
            throw "review_admin_bootstrap_file_missing"
        }
        $bootstrapCode = [System.IO.File]::ReadAllText($bootstrapPath).Trim()
        Remove-Item -LiteralPath $bootstrapPath -Force
        if ($bootstrapCode.Length -lt 32) {
            throw "review_admin_bootstrap_file_invalid"
        }

        if ($OpenBrowser) {
            if (-not (Test-Path -LiteralPath $chromePath -PathType Leaf)) {
                throw "review_admin_chrome_not_found"
            }
            New-Item -ItemType Directory -Path $chromeProfile -Force | Out-Null
            $encodedBootstrap = [System.Uri]::EscapeDataString($bootstrapCode)
            $browserUrl = "$adminUrl#nia-bootstrap=$encodedBootstrap"
            $chromeProcess = Start-Process -FilePath $chromePath -PassThru -ArgumentList @(
                "--user-data-dir=$chromeProfile",
                "--no-first-run",
                "--allow-insecure-localhost",
                "--new-window",
                $browserUrl
            )
            $encodedBootstrap = $null
            $browserUrl = $adminUrl
        }
        else {
            Write-Host "BOOTSTRAP DE UN SOLO USO (5 MIN): $bootstrapCode"
        }
        $bootstrapCode = $null

        Read-Host "Review Admin listo. Presiona ENTER para cerrar limpiamente" | Out-Null
        [System.IO.File]::WriteAllText($stopPath, "stop")
        if (-not $pythonProcess.WaitForExit(20000)) {
            throw "review_admin_server_graceful_shutdown_timeout"
        }
        if ($pythonProcess.ExitCode -ne 0) {
            throw "review_admin_server_failed_$($pythonProcess.ExitCode)"
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    if ($null -ne $pythonProcess -and -not $pythonProcess.HasExited) {
        if (-not (Test-Path -LiteralPath $stopPath)) {
            [System.IO.File]::WriteAllText($stopPath, "stop")
        }
        if (-not $pythonProcess.WaitForExit(5000)) {
            Stop-Process -Id $pythonProcess.Id -Force -ErrorAction SilentlyContinue
        }
    }
    if ($null -ne $chromeProcess -and -not $chromeProcess.HasExited) {
        Stop-Process -Id $chromeProcess.Id -Force -ErrorAction SilentlyContinue
        $chromeProcess.WaitForExit(5000) | Out-Null
    }
    if (Test-Path -LiteralPath $chromeProfile) {
        Stop-IsolatedChrome -ProfilePath $chromeProfile
    }
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
