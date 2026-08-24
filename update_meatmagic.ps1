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
# ============================================================

$ErrorActionPreference = 'Stop'

# ---- EDIT THESE TWO LINES ----
$RepoOwner = 'hamisi99-03'
$RepoName  = 'hi_frontoffice'
# ------------------------------

$ExeName   = 'MEATMAGIC.exe'
$ProcName  = 'MEATMAGIC'

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$VersionFile = Join-Path $ScriptDir 'version.txt'
$ExePath     = Join-Path $ScriptDir $ExeName

Set-Location $ScriptDir

Write-Host 'MeatMagic updater - checking for a new version...'

$release = Invoke-RestMethod -Uri "https://api.github.com/repos/$RepoOwner/$RepoName/releases/latest" -Headers @{ 'User-Agent' = 'meatmagic-updater' }

$asset = $release.assets | Where-Object { $_.name -eq $ExeName } | Select-Object -First 1
if (-not $asset) {
    Write-Host 'ERROR: no MEATMAGIC.exe attached to the latest GitHub release.' -ForegroundColor Red
    Write-Host '       Create a release and attach dist\MEATMAGIC.exe to it.'
    exit 1
}

$latestTag = $release.tag_name
$currentTag = ''
if (Test-Path $VersionFile) { $currentTag = (Get-Content $VersionFile -Raw).Trim() }

if ($currentTag -eq $latestTag) {
    Write-Host "Already up to date ($latestTag)."
} else {
    Write-Host "New version available: $latestTag (you have: $currentTag)"
    Write-Host 'Downloading...'
    $tmp = Join-Path $ScriptDir 'MEATMAGIC.exe.new'
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $tmp

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
