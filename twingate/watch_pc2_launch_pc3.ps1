
# watch_pc2_launch_pc3.ps1
# Runs as an independent process — waits for pc2 to finish then launches pc3

$PC2Log   = "C:\Users\sahil\dt-sionna-rt\twingate\out\a15_pc2_run.log"
$PC3Log   = "C:\Users\sahil\dt-sionna-rt\twingate\out\a15_pc3_run.log"
$PC3Err   = "C:\Users\sahil\dt-sionna-rt\twingate\out\a15_pc3_run.err"
$WorkDir  = "C:\Users\sahil\dt-sionna-rt\twingate"
$WatchLog = "C:\Users\sahil\dt-sionna-rt\twingate\out\watcher_pc2_pc3.log"

"[$(Get-Date -Format 'HH:mm:ss')] Watcher started — monitoring pc2 log for FINAL RESULTS" | Out-File $WatchLog -Append

while (-not (Select-String -Path $PC2Log -Pattern "FINAL RESULTS" -Quiet -ErrorAction SilentlyContinue)) {
    Start-Sleep -Seconds 60
    "[$(Get-Date -Format 'HH:mm:ss')] Still waiting for pc2..." | Out-File $WatchLog -Append
}

"[$(Get-Date -Format 'HH:mm:ss')] pc2 FINAL RESULTS detected. Cleaning up..." | Out-File $WatchLog -Append

# Kill zombie GPU processes
$gpuPids = (nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>$null)
foreach ($p in $gpuPids) {
    $p = $p.Trim()
    if ($p -match '^\d+$') {
        "[$(Get-Date -Format 'HH:mm:ss')] Stopping GPU PID $p" | Out-File $WatchLog -Append
        Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
    }
}
Start-Sleep -Seconds 8

# Clear DrJIT cache
Remove-Item "C:\Users\sahil\AppData\Local\Temp\drjit\optix7cache.db*" -Force -ErrorAction SilentlyContinue
"[$(Get-Date -Format 'HH:mm:ss')] Cache cleared." | Out-File $WatchLog -Append
Start-Sleep -Seconds 5

# Launch pc3
$proc = Start-Process -FilePath "python" `
    -ArgumentList "-u", "A15_pc3.py" `
    -WorkingDirectory $WorkDir `
    -RedirectStandardOutput $PC3Log `
    -RedirectStandardError $PC3Err `
    -WindowStyle Hidden -PassThru
"[$(Get-Date -Format 'HH:mm:ss')] pc3 launched PID: $($proc.Id)" | Out-File $WatchLog -Append
