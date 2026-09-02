# ============================================================
#  MeatMagic self-updater (run on the SHOP computer)
#  Downloads the latest MEATMAGIC.exe from a GitHub release,
#  swaps it in and restarts the app. No Python needed here.
#
#  HOW TO USE
#    - Copy this file + update_meatmagic.bat into the folder
#      that already contains MEATMAGIC.exe (and db.sqlite3).
#    - Fill in the two values below (your GitHub username and
#      the repository name).
#    - Double-click update_meatmagic.bat whenever you want to
#      check for a new version (or schedule it, see README).
#
#  Your database (db.sqlite3) and secret key (meatmagic.key)
#  are NEVER touched - only MEATMAGIC.exe is replaced.
#
#  NOTE: this script does NOT call the GitHub API, so it is
#  not affected by the 60-request-per-hour rate limit.
# ============================================================

$ErrorActionPreference = 'Stop'

# ---- EDIT THESE TWO LINES ----
$RepoOwner = 'hamisi99-03'
$RepoName  = 'hi_frontoffice'
# ------------------------------

$ExeName   = 'MEATMAGIC.exe'
$ProcName  = 'MEATMAGIC'

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$VersionFile = Join-Path $ScriptDir 'version.txt'
$ExePath     = Join-Path $ScriptDir $ExeName
$LatestUrl   = "https://github.com/$RepoOwner/$RepoName/releases/latest/download/$ExeName"

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

Set-Location $ScriptDir

Write-Host 'MeatMagic updater - checking for a new version...'

# Find the latest release tag by reading the redirect Location of the
# "latest/download" URL (no API call, so no rate limit).
$latestTag = $null
$req = [System.Net.HttpWebRequest]::Create($LatestUrl)
$req.Method = 'HEAD'
$req.AllowAutoRedirect = $false
$req.UserAgent = 'meatmagic-updater'
$req.Timeout = 30000
try {
    $resp = $req.GetResponse()
} catch {
    $resp = $_.Exception.Response
}
$location = $null
if ($resp) {
    $location = $resp.Headers['Location']
    $resp.Close()
}
if ($location -and $location -match '/releases/download/([^/]+)/') {
    $latestTag = $Matches[1]
}

if (-not $latestTag) {
    Write-Host 'ERROR: could not find the latest MEATMAGIC.exe release.' -ForegroundColor Red
    Write-Host '       Create a release and attach dist\MEATMAGIC.exe to it.'
    exit 1
}

$currentTag = ''
if (Test-Path $VersionFile) { $currentTag = (Get-Content $VersionFile -Raw).Trim() }

if ($currentTag -eq $latestTag) {
    Write-Host "Already up to date ($latestTag)."
} else {
    Write-Host "New version available: $latestTag (you have: $currentTag)"
    Write-Host 'Downloading...'
    $tmp = Join-Path $ScriptDir 'MEATMAGIC.exe.new'
    Invoke-WebRequest -Uri $LatestUrl -OutFile $tmp -UseBasicParsing

    $running = Get-Process -Name $ProcName -ErrorAction SilentlyContinue
    if ($running) {
        Write-Host 'Stopping MEATMAGIC...'
        $running | Stop-Process -Force
        Start-Sleep -Seconds 3
    }

    $old = Join-Path $ScriptDir 'MEATMAGIC.exe.old'
    if (Test-Path $old) { Remove-Item $old -Force }
    if (Test-Path $ExePath) { Rename-Item $ExePath 'MEATMAGIC.exe.old' }
    Rename-Item $tmp $ExeName

    Set-Content -Path $VersionFile -Value $latestTag
    Write-Host "Updated to $latestTag."
}

Write-Host 'Starting MEATMAGIC...'
Start-Process -FilePath $ExePath
Write-Host 'Done.'
