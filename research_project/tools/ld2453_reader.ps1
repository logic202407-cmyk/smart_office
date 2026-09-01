<#+
.SYNOPSIS
Captures HLK-LD2453 frames to JSONL without Python dependencies.

.EXAMPLE
powershell.exe -ExecutionPolicy Bypass -File .\tools\ld2453_reader.ps1 -SelfTest
powershell.exe -ExecutionPolicy Bypass -File .\tools\ld2453_reader.ps1 -Port COM7 -Output .\ei_experiments\raw\ld2453_pilot_r01.jsonl
powershell.exe -ExecutionPolicy Bypass -File .\tools\ld2453_reader.ps1 -Port COM7 -Output .\ei_experiments\raw\ld2453_comm_selfcheck_r01.jsonl -TrialId ld2453_comm_selfcheck_r01 -Scenario comm_selfcheck -DurationSeconds 30
#>
[CmdletBinding()]
param(
    [string]$Port,
    [int]$Baud = 256000,
    [string]$Output,
    [string]$TrialId,
    [string]$Scenario,
    [string]$MetaOutput,
    [int]$DurationSeconds = 0,
    [switch]$SelfTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

[byte[]]$FrameHeader = 0xAA, 0xFF, 0x03, 0x00
[byte[]]$FrameTail = 0x55, 0xCC
$TargetBytes = 8
$FrameBytes = 30

function ConvertFrom-LD2453SignedMagnitude {
    param([UInt16]$Value)
    [int]$magnitude = $Value -band 0x7FFF
    if ($magnitude -eq 0) { return 0 }
    if (($Value -band 0x8000) -ne 0) { return $magnitude }
    return -$magnitude
}

function ConvertFrom-LD2453Frame {
    param([byte[]]$Frame)
    if ($Frame.Length -ne $FrameBytes) { throw "Invalid frame length: $($Frame.Length)" }
    for ($i = 0; $i -lt 4; $i++) {
        if ($Frame[$i] -ne $FrameHeader[$i]) { throw 'Invalid frame header' }
    }
    if ($Frame[28] -ne $FrameTail[0] -or $Frame[29] -ne $FrameTail[1]) { throw 'Invalid frame tail' }

    $targets = [System.Collections.Generic.List[object]]::new()
    for ($slot = 1; $slot -le 3; $slot++) {
        $offset = 4 + (($slot - 1) * $TargetBytes)
        $isEmpty = $true
        for ($i = 0; $i -lt $TargetBytes; $i++) {
            if ($Frame[$offset + $i] -ne 0) { $isEmpty = $false; break }
        }
        if ($isEmpty) { continue }
        [UInt16]$xRaw = [BitConverter]::ToUInt16($Frame, $offset)
        [UInt16]$yRaw = [BitConverter]::ToUInt16($Frame, $offset + 2)
        [UInt16]$speedRaw = [BitConverter]::ToUInt16($Frame, $offset + 4)
        [UInt16]$distanceMm = [BitConverter]::ToUInt16($Frame, $offset + 6)
        $targets.Add([ordered]@{
            slot = $slot
            x_mm = ConvertFrom-LD2453SignedMagnitude $xRaw
            y_mm = ConvertFrom-LD2453SignedMagnitude $yRaw
            speed_cm_s = ConvertFrom-LD2453SignedMagnitude $speedRaw
            pixel_distance_mm = $distanceMm
        })
    }
    return ,$targets.ToArray()
}

function Find-LD2453Header {
    param([System.Collections.Generic.List[byte]]$Buffer)
    for ($i = 0; $i -le $Buffer.Count - 4; $i++) {
        if ($Buffer[$i] -eq 0xAA -and $Buffer[$i + 1] -eq 0xFF -and
            $Buffer[$i + 2] -eq 0x03 -and $Buffer[$i + 3] -eq 0x00) { return $i }
    }
    return -1
}

function Test-LD2453Parser {
    [byte[]]$example = 0xAA,0xFF,0x03,0x00,0x0E,0x03,0xB1,0x86,0x10,0x00,0x68,0x01,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x55,0xCC
    $target = (ConvertFrom-LD2453Frame $example)[0]
    if ($target.slot -ne 1 -or $target.x_mm -ne -782 -or $target.y_mm -ne 1713 -or
        $target.speed_cm_s -ne -16 -or $target.pixel_distance_mm -ne 360) {
        throw "Parser self-test mismatch: $($target | ConvertTo-Json -Compress)"
    }
    Write-Host 'LD2453 parser self-test: PASS'
}

if ($SelfTest) { Test-LD2453Parser; exit 0 }
if ([string]::IsNullOrWhiteSpace($Port) -or [string]::IsNullOrWhiteSpace($Output)) {
    throw 'Specify -Port and -Output, or use -SelfTest.'
}

$outputPath = [System.IO.Path]::GetFullPath($Output)
$outputDir = Split-Path -Parent $outputPath
[System.IO.Directory]::CreateDirectory($outputDir) | Out-Null
if ([string]::IsNullOrWhiteSpace($TrialId)) {
    $TrialId = [System.IO.Path]::GetFileNameWithoutExtension($outputPath)
}
if ([string]::IsNullOrWhiteSpace($Scenario)) {
    $Scenario = 'unspecified'
}
if ([string]::IsNullOrWhiteSpace($MetaOutput)) {
    $MetaOutput = [System.IO.Path]::ChangeExtension($outputPath, '.metadata.json')
}
$metaPath = [System.IO.Path]::GetFullPath($MetaOutput)
$metaDir = Split-Path -Parent $metaPath
if (-not [string]::IsNullOrWhiteSpace($metaDir)) {
    [System.IO.Directory]::CreateDirectory($metaDir) | Out-Null
}
$serial = [System.IO.Ports.SerialPort]::new($Port, $Baud, [System.IO.Ports.Parity]::None, 8, [System.IO.Ports.StopBits]::One)
$serial.ReadTimeout = 200
$serial.Open()
$writer = [System.IO.StreamWriter]::new($outputPath, $true, [System.Text.UTF8Encoding]::new($false))
$buffer = [System.Collections.Generic.List[byte]]::new()
$start = [System.Diagnostics.Stopwatch]::StartNew()
$startedUtc = (Get-Date).ToUniversalTime().ToString('o')
$parseErrors = 0
$recordCount = 0
$targetHistogram = [ordered]@{ '0' = 0; '1' = 0; '2' = 0; '3' = 0 }

try {
    if ($DurationSeconds -gt 0) {
        Write-Host "Capturing $Port at $Baud baud for $DurationSeconds seconds."
    } else {
        Write-Host "Capturing $Port at $Baud baud. Press Ctrl+C to stop."
    }
    while ($true) {
        if ($DurationSeconds -gt 0 -and $start.Elapsed.TotalSeconds -ge $DurationSeconds) { break }
        if ($serial.BytesToRead -gt 0) {
            [byte[]]$incoming = New-Object byte[] $serial.BytesToRead
            [void]$serial.Read($incoming, 0, $incoming.Length)
            $buffer.AddRange($incoming)
        } else {
            Start-Sleep -Milliseconds 10
        }
        while ($true) {
            $headerAt = Find-LD2453Header $buffer
            if ($headerAt -lt 0) {
                if ($buffer.Count -gt 3) { $buffer.RemoveRange(0, $buffer.Count - 3) }
                break
            }
            if ($headerAt -gt 0) { $buffer.RemoveRange(0, $headerAt) }
            if ($buffer.Count -lt $FrameBytes) { break }
            [byte[]]$frame = $buffer.GetRange(0, $FrameBytes).ToArray()
            if ($frame[28] -ne $FrameTail[0] -or $frame[29] -ne $FrameTail[1]) {
                $parseErrors++
                $buffer.RemoveAt(0)
                continue
            }
            $buffer.RemoveRange(0, $FrameBytes)
            $targets = @(ConvertFrom-LD2453Frame $frame)
            $targetKey = [string]$targets.Count
            if ($targetHistogram.Contains($targetKey)) {
                $targetHistogram[$targetKey]++
            }
            $recordCount++
            $record = [ordered]@{
                type = 'ld2453_targets'
                t_ms = $start.ElapsedMilliseconds
                targets = $targets
                raw_hex = (($frame | ForEach-Object { $_.ToString('x2') }) -join '')
            }
            $line = $record | ConvertTo-Json -Compress -Depth 4
            Write-Output $line
            $writer.WriteLine($line)
            $writer.Flush()
        }
    }
} finally {
    $finishedUtc = (Get-Date).ToUniversalTime().ToString('o')
    $metadata = [ordered]@{
        schema_version = '1.0'
        trial_id = $TrialId
        scenario = $Scenario
        transport = [ordered]@{
            kind = 'serial'
            port = $Port
            baud = $Baud
        }
        capture_started_utc = $startedUtc
        capture_finished_utc = $finishedUtc
        clock_anchors = @(
            [ordered]@{ wall_utc = $startedUtc; monotonic_ms = 0 },
            [ordered]@{ wall_utc = $finishedUtc; monotonic_ms = $start.ElapsedMilliseconds }
        )
        record_counts = [ordered]@{
            ld2453_targets = $recordCount
            parse_errors = $parseErrors
        }
        target_count_histogram = $targetHistogram
        data_status = 'raw_complete_pending_annotation'
    }
    $metadata | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $metaPath -Encoding UTF8
    $writer.Dispose()
    $serial.Dispose()
}
