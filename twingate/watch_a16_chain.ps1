# watch_a16_chain.ps1
# Runs as an independent process.
# Waits for pc1 to finish, then auto-launches pc4 -> pc2 -> pc3 in sequence.
# Each launch waits for the previous to complete before starting the next.

$WorkDir  = "C:\Users\sahil\dt-sionna-rt\twingate"
$WatchLog = "$WorkDir\out\a16_chain_watcher.log"
$DrJIT    = "C:\Users\sahil\AppData\Local\Temp\drjit\optix7cache.db*"

function Log($msg) {
    $line = "[$(Get-Date -Format 'HH:mm:ss')] $msg"
    $line | Out-File $WatchLog -Append
    Write-Host $line
}

function ClearGPU {
    $pids = (nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>$null)
    foreach ($p in $pids) {
        $p = $p.Trim()
        if ($p -match '^\d+$') {
            Stop-Process -Id ([int]$p) -Force -ErrorAction SilentlyContinue
            Log "  Stopped GPU PID $p"
        }
    }
    Start-Sleep -Seconds 8
    Remove-Item $DrJIT -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
    Log "  GPU cleared + DrJIT cache removed"
}

function WaitForFinish($logFile, $label) {
    Log "Waiting for $label to finish..."
    while (-not (Select-String -Path $logFile -Pattern "FINAL RESULTS" -Quiet -ErrorAction SilentlyContinue)) {
        Start-Sleep -Seconds 60
    }
    Log "$label FINISHED."
}

function LaunchAndWait($script, $logOut, $logErr, $label) {
    ClearGPU
    $proc = Start-Process -FilePath "python" `
        -ArgumentList "-u", $script `
        -WorkingDirectory $WorkDir `
        -RedirectStandardOutput $logOut `
        -RedirectStandardError  $logErr `
        -WindowStyle Hidden -PassThru
    Log "Launched $label  PID=$($proc.Id)"
    WaitForFinish $logOut $label
}

Log "=== A16 chain watcher started ==="
Log "Order: pc1 (already running) -> pc4 -> pc2 -> pc3"

# ── Wait for pc1 ──────────────────────────────────────────────────────────────
WaitForFinish "$WorkDir\out\a16_pc1_run.log" "pc1"

# ── pc4 ───────────────────────────────────────────────────────────────────────
LaunchAndWait "A16_pc4.py" "$WorkDir\out\a16_pc4_run.log" "$WorkDir\out\a16_pc4_run.err" "pc4"

# ── pc2 ───────────────────────────────────────────────────────────────────────
LaunchAndWait "A16_pc2.py" "$WorkDir\out\a16_pc2_run.log" "$WorkDir\out\a16_pc2_run.err" "pc2"

# ── pc3 ───────────────────────────────────────────────────────────────────────
LaunchAndWait "A16_pc3.py" "$WorkDir\out\a16_pc3_run.log" "$WorkDir\out\a16_pc3_run.err" "pc3"

# ── All done ──────────────────────────────────────────────────────────────────
Log "=== ALL A16 RUNS COMPLETE (pc1 + pc4 + pc2 + pc3) ==="

# Windows toast notification
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.MessageBox]::Show(
    "All A16 runs finished (pc1+pc4+pc2+pc3). Check out/a16_chain_watcher.log for details.",
    "TWINGATE A16 Done",
    [System.Windows.Forms.MessageBoxButtons]::OK,
    [System.Windows.Forms.MessageBoxIcon]::Information
) | Out-Null
