<#
.SYNOPSIS
  Phase 6b: prove a Release zip installs on a clean Windows with no Python,
  no MSYS2 and no VC++ redistributable -- in Windows Sandbox.

.DESCRIPTION
  Downloads the tag's agent zip and its sums from GitHub Releases into a temp
  folder, writes a .wsb that maps that folder read-only into a fresh sandbox
  and runs a check script at logon, then opens the sandbox. The check script
  verifies the zip's sha256 against the published sum, unzips, and runs:

      ak820 --version      (runs at all: static CRT, nothing to install)
      ak820 list           (discovery with no board: 0 of N, no error)
      ak820 probe          (SMTC with no media: no sessions, no error)
      ak820 install --clock
      ak820 status         (the gate: board=absent, updated moving, no [warn])

  and leaves the window open with the daemon's log. With -Wait, the same
  output is read back from the mapped folder and printed here on the host,
  so the run can be driven and judged without touching the sandbox window. The sandbox has no USB
  passthrough, so the board half of the install is proven on a real machine;
  this proves the "nothing else needed" half. Close the sandbox and every
  trace of the install is discarded.

  Once, elevated, then reboot (Windows 10/11 Pro, Enterprise or Education):

      Enable-WindowsOptionalFeature -Online -FeatureName Containers-DisposableClientVM -All

.PARAMETER Tag
  The release tag, e.g. v0.1.0.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\sandbox-6b.ps1 -Tag v0.1.0
#>
param(
    [Parameter(Mandatory = $true)][string]$Tag,
    # Wait for the sandbox to finish and print its transcript here on the host.
    [switch]$Wait
)
$ErrorActionPreference = 'Stop'

$sandbox = Join-Path $env:WINDIR 'System32\WindowsSandbox.exe'
if (-not (Test-Path $sandbox)) {
    throw "Windows Sandbox is not enabled. Once, from an elevated PowerShell, then reboot:`n  Enable-WindowsOptionalFeature -Online -FeatureName Containers-DisposableClientVM -All"
}

$repo = 'jdlien/ak820-pro'
$zip = "ak820-agent-$Tag-windows-x64.zip"
$dir = Join-Path $env:TEMP "ak820-sandbox-$Tag"
New-Item -ItemType Directory -Force $dir | Out-Null
foreach ($name in @($zip, 'sha256sums.txt')) {
    $url = "https://github.com/$repo/releases/download/$Tag/$name"
    "downloading $url"
    Invoke-WebRequest -Uri $url -OutFile (Join-Path $dir $name)
}

# Runs INSIDE the sandbox, as WDAGUtilityAccount, at logon.
$check = @"
`$ErrorActionPreference = 'Continue'
# Everything below lands in result.txt in the mapped folder -- on the HOST, so
# whoever launched this can read the outcome without looking at this window.
Start-Transcript -Path 'C:\Users\WDAGUtilityAccount\Desktop\ak820\result.txt' -Force | Out-Null
`$host.UI.RawUI.WindowTitle = 'ak820 phase 6b: $Tag on a clean Windows'
`$src = 'C:\Users\WDAGUtilityAccount\Desktop\ak820'
`$work = 'C:\Users\WDAGUtilityAccount\ak820'
Set-Location `$src
Write-Host "== sha256 of the zip against the published sum" -ForegroundColor Cyan
`$have = (Get-FileHash '$zip' -Algorithm SHA256).Hash.ToLower()
`$want = ((Get-Content sha256sums.txt | Select-String '$zip') -split '\s+')[0]
if (`$have -eq `$want) { Write-Host "OK  `$have" -ForegroundColor Green } else { Write-Host "MISMATCH have `$have want `$want" -ForegroundColor Red }
Expand-Archive -Path '$zip' -DestinationPath `$work -Force
Set-Location (Join-Path `$work 'ak820-agent-$Tag-windows-x64')
foreach (`$cmd in @('--version', 'list', 'probe', 'install --clock')) {
    Write-Host "`n== ak820 `$cmd" -ForegroundColor Cyan
    & .\ak820.exe (`$cmd -split ' ')
    Write-Host "exit `$LASTEXITCODE"
}
Start-Sleep -Seconds 6
Write-Host "`n== ak820 status  (the gate: board=absent, updated moving, no [warn] lines)" -ForegroundColor Cyan
& .\ak820.exe status
Write-Host "`n== the log" -ForegroundColor Cyan
Get-Content "`$env:LOCALAPPDATA\ak820pro\ak820-agent.log"
Write-Host "`nDone. Close this sandbox window to discard everything." -ForegroundColor Yellow
Stop-Transcript | Out-Null
"@
Set-Content -Path (Join-Path $dir 'check.ps1') -Value $check

$wsb = @"
<Configuration>
  <MappedFolders>
    <MappedFolder>
      <HostFolder>$dir</HostFolder>
      <SandboxFolder>C:\Users\WDAGUtilityAccount\Desktop\ak820</SandboxFolder>
      <ReadOnly>false</ReadOnly>
    </MappedFolder>
  </MappedFolders>
  <LogonCommand>
    <Command>powershell -NoExit -ExecutionPolicy Bypass -File C:\Users\WDAGUtilityAccount\Desktop\ak820\check.ps1</Command>
  </LogonCommand>
</Configuration>
"@
$wsbPath = Join-Path $dir 'ak820-6b.wsb'
Set-Content -Path $wsbPath -Value $wsb
"opening the sandbox from $wsbPath"
Start-Process $wsbPath

if ($Wait) {
    $result = Join-Path $dir 'result.txt'
    Remove-Item $result -ErrorAction SilentlyContinue
    $deadline = (Get-Date).AddMinutes(6)
    while ((Get-Date) -lt $deadline) {
        if ((Test-Path $result) -and (Select-String -Path $result -Pattern '^Done\.' -Quiet)) { break }
        Start-Sleep -Seconds 5
    }
    if (Test-Path $result) { Get-Content $result } else { throw "no result.txt from the sandbox after 6 minutes" }
}
