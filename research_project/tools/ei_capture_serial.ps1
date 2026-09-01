<#
Captures SmartOffice USB-CDC lines into an append-only JSONL experiment record.
It is intentionally read-only: no serial command is sent to the device.

Example:
  .\tools\ei_capture_serial.ps1 -Port COM13 -TrialId link_check_001 -DurationSeconds 30 -Scenario link_check
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Port,
    [Parameter(Mandatory = $true)][string]$TrialId,
    [Parameter(Mandatory = $true)][ValidateRange(0.1, 86400)][double]$DurationSeconds,
    [int]$Baud = 115200,
    [string]$Scenario = '',
    [string]$OperatorId = '',
    [string]$OutputDirectory = 'ei_experiments\raw'
)

$ErrorActionPreference = 'Stop'

function Get-UtcTimestamp {
    return [DateTime]::UtcNow.ToString('o')
}

$safeId = ($TrialId -replace '[^A-Za-z0-9_-]', '_').Trim('_')
if ([string]::IsNullOrWhiteSpace($safeId)) { $safeId = 'trial' }
$outDir = [IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputDirectory))
[IO.Directory]::CreateDirectory($outDir) | Out-Null
$jsonlPath = Join-Path $outDir ($safeId + '.jsonl')
$metaPath = Join-Path $outDir ($safeId + '.metadata.json')
if ((Test-Path -LiteralPath $jsonlPath) -or (Test-Path -LiteralPath $metaPath)) {
    throw "Refusing to overwrite an existing trial: $TrialId"
}

$metadata = [ordered]@{
    schema_version = '1.0'
    trial_id = $TrialId
    operator = $OperatorId
    scenario = $Scenario
    serial = [ordered]@{ port = $Port; baud = $Baud; timeout_s = 0.25 }
    capture_started_utc = Get-UtcTimestamp
    requested_duration_s = $DurationSeconds
    tool = 'tools/ei_capture_serial.ps1'
    data_status = 'raw_unreviewed'
}
[IO.File]::WriteAllText($metaPath, ($metadata | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))

$counts = [ordered]@{ measurement = 0; state = 0; heartbeat = 0; json_other = 0; json_non_object = 0; non_json = 0 }
$serial = [System.IO.Ports.SerialPort]::new($Port, $Baud, [System.IO.Ports.Parity]::None, 8, [System.IO.Ports.StopBits]::One)
$serial.ReadTimeout = 250
$serial.NewLine = "`n"
$sw = [Diagnostics.Stopwatch]::StartNew()
$writer = $null

try {
    $serial.Open()
    $writer = [IO.StreamWriter]::new($jsonlPath, $false, [Text.UTF8Encoding]::new($false))
    Write-Host "Capturing $Port at $Baud baud for $DurationSeconds seconds -> $jsonlPath"
    while ($sw.Elapsed.TotalSeconds -lt $DurationSeconds) {
        try {
            $raw = $serial.ReadLine().TrimEnd("`r", "`n")
        } catch [TimeoutException] {
            continue
        }
        $record = [ordered]@{
            received_at_utc = Get-UtcTimestamp
            elapsed_s = [Math]::Round($sw.Elapsed.TotalSeconds, 6)
            raw_utf8 = $raw
        }
        try {
            $payload = $raw | ConvertFrom-Json -ErrorAction Stop
            $record.payload = $payload
            if ($null -eq $payload -or $payload -isnot [psobject]) {
                $kind = 'json_non_object'
            } elseif ($payload.type -eq 'heartbeat') {
                $kind = 'heartbeat'
            } elseif ($payload.type -eq 'measurement') {
                $kind = 'measurement'
            } elseif ($payload.state -in @('NORMAL','HUMAN_DETECTED','APPROACHING','SUSPECTED_PEEPING','PRIVACY_PROTECT','ALARM')) {
                $kind = 'state'
            } else {
                $kind = 'json_other'
            }
        } catch {
            $kind = 'non_json'
        }
        $record.record_type = $kind
        $counts[$kind]++
        $writer.WriteLine(($record | ConvertTo-Json -Depth 8 -Compress))
        $writer.Flush()
    }
} finally {
    if ($null -ne $writer) { $writer.Dispose() }
    if ($serial.IsOpen) { $serial.Close() }
    $sw.Stop()
}

$metadata.capture_finished_utc = Get-UtcTimestamp
$metadata.actual_duration_s = [Math]::Round($sw.Elapsed.TotalSeconds, 3)
$metadata.record_counts = $counts
$metadata.data_status = 'raw_complete_pending_annotation'
[IO.File]::WriteAllText($metaPath, ($metadata | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Host ('Capture complete: ' + ($counts | ConvertTo-Json -Compress))
