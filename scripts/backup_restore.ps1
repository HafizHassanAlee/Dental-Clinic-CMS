<#
.SYNOPSIS
    Database & Private Clinical Uploads Backup and Restore Script for Rumi Dental Care.

.DESCRIPTION
    Supports creating timestamped PostgreSQL dumps (`pg_dump`) + archiving `private_uploads/`,
    or restoring a PostgreSQL dump (`psql`) into the target database.

.EXAMPLE
    .\scripts\backup_restore.ps1 -Action backup
    .\scripts\backup_restore.ps1 -Action restore -BackupFile ".\backups\rumi_dental_20261019_190000.sql"
#>

param (
    [Parameter(Mandatory = $false)]
    [ValidateSet("backup", "restore")]
    [string]$Action = "backup",

    [Parameter(Mandatory = $false)]
    [string]$DbHost = "localhost",

    [Parameter(Mandatory = $false)]
    [string]$DbPort = "5432",

    [Parameter(Mandatory = $false)]
    [string]$DbUser = "postgres",

    [Parameter(Mandatory = $false)]
    [string]$DbName = "rumi_dental",

    [Parameter(Mandatory = $false)]
    [string]$BackupFile = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackupDir = Join-Path $ProjectRoot "backups"
if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir | Out-Null
}

# Locate PostgreSQL binaries (PATH or local installation)
$PgBinDir = "C:\Users\DELL\Downloads\postgreSQL\bin"
$PgDumpExe = if (Test-Path (Join-Path $PgBinDir "pg_dump.exe")) { Join-Path $PgBinDir "pg_dump.exe" } else { "pg_dump" }
$PsqlExe = if (Test-Path (Join-Path $PgBinDir "psql.exe")) { Join-Path $PgBinDir "psql.exe" } else { "psql" }

if ($Action -eq "backup") {
    $Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $SqlDumpPath = Join-Path $BackupDir "${DbName}_${Timestamp}.sql"
    $UploadsZipPath = Join-Path $BackupDir "private_uploads_${Timestamp}.zip"

    Write-Host "[1/2] Backing up PostgreSQL database '$DbName' to $SqlDumpPath ..." -ForegroundColor Cyan
    & $PgDumpExe -h $DbHost -p $DbPort -U $DbUser -d $DbName -F p -f $SqlDumpPath

    $UploadsDir = Join-Path $ProjectRoot "backend\private_uploads"
    if (Test-Path $UploadsDir) {
        Write-Host "[2/2] Archiving private clinical uploads to $UploadsZipPath ..." -ForegroundColor Cyan
        Compress-Archive -Path "$UploadsDir\*" -DestinationPath $UploadsZipPath -Force -ErrorAction SilentlyContinue
    }
    Write-Host "SUCCESS: Backup completed in $BackupDir" -ForegroundColor Green
}
elseif ($Action -eq "restore") {
    if (-not $BackupFile -or -not (Test-Path $BackupFile)) {
        throw "Please specify an existing -BackupFile path to restore."
    }
    Write-Host "Restoring PostgreSQL database '$DbName' from $BackupFile ..." -ForegroundColor Yellow
    & $PsqlExe -h $DbHost -p $DbPort -U $DbUser -d $DbName -f $BackupFile
    Write-Host "SUCCESS: Database '$DbName' restored from $BackupFile" -ForegroundColor Green
}
