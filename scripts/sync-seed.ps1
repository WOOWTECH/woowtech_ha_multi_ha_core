# Materialize _seed\ into every add-on's build context (Windows/PowerShell equivalent of sync-seed.sh).
# Run after vendoring, or whenever _seed\ changes:  pwsh scripts\sync-seed.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$seed = Join-Path $root "_seed"

foreach ($n in 1..5) {
    $dest = Join-Path $root "woow_ha_core_$n\rootfs\opt\woow_seed"
    if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    Copy-Item -Recurse -Force (Join-Path $seed "custom_components") (Join-Path $dest "custom_components")
    Copy-Item -Recurse -Force (Join-Path $seed "config_defaults")   (Join-Path $dest "config_defaults")
    Copy-Item -Force (Join-Path $seed "woow_seed.sh") (Join-Path $dest "woow_seed.sh")
    Write-Host "synced -> woow_ha_core_$n\rootfs\opt\woow_seed"
}
