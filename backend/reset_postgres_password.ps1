# Resets the PostgreSQL 'postgres' superuser password to 'postgres'.
# Run from an Administrator PowerShell prompt:
#   powershell -ExecutionPolicy Bypass -File reset_postgres_password.ps1
#
# What it does:
#   1. Backs up pg_hba.conf
#   2. Switches local auth to 'trust' (no password required)
#   3. Restarts the Postgres service
#   4. Runs ALTER USER postgres WITH PASSWORD 'postgres'
#   5. Restores pg_hba.conf from the backup
#   6. Restarts the service again

$ErrorActionPreference = "Stop"

$pgDir     = "C:\Program Files\PostgreSQL\15"
$hbaFile   = "$pgDir\data\pg_hba.conf"
$backup    = "$pgDir\data\pg_hba.conf.bak"
$psql      = "$pgDir\bin\psql.exe"
$service   = "postgresql-x64-15"

Write-Host "==> Backing up pg_hba.conf"
Copy-Item $hbaFile $backup -Force

Write-Host "==> Switching local auth to trust"
(Get-Content $hbaFile) `
    -replace '^(host\s+all\s+all\s+127\.0\.0\.1/32\s+).*$', '$1trust' `
    -replace '^(host\s+all\s+all\s+::1/128\s+).*$',        '$1trust' |
    Set-Content $hbaFile

Write-Host "==> Restarting $service"
Restart-Service $service

Start-Sleep -Seconds 3

Write-Host "==> Setting password"
& $psql -U postgres -h localhost -c "ALTER USER postgres WITH PASSWORD 'postgres';"

Write-Host "==> Restoring pg_hba.conf"
Move-Item $backup $hbaFile -Force

Write-Host "==> Restarting $service"
Restart-Service $service

Write-Host ""
Write-Host "DONE. Password is now: postgres"
Write-Host "Test with: `"$psql`" -U postgres -h localhost"
