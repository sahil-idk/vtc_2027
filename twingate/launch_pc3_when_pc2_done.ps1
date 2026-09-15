# Waits for pc2 full-mode v2 to finish, then launches pc3
$pc2_log = "C:\Users\sahil\dt-sionna-rt\twingate\out\a15_pc2_fullv2.log"
$pc2_csv = "C:\Users\sahil\dt-sionna-rt\twingate\out\pc2_refinement_results.csv"

Write-Host "Waiting for pc2 to finish..."
while ($true) {
    Start-Sleep -Seconds 60
    $last = Get-Content $pc2_log -Tail 5 2>$null
    if ($last -match "Total Sionna calls") {
        Write-Host "pc2 done. Launching pc3..."
        break
    }
    $done = if (Test-Path $pc2_csv) { (Get-Content $pc2_csv | Measure-Object -Line).Lines - 1 } else { 0 }
    Write-Host "$(Get-Date -Format 'HH:mm')  pc2: $done towers done so far..."
}

$log = "C:\Users\sahil\dt-sionna-rt\twingate\out\a15_pc3_fullv2.log"
$err = "C:\Users\sahil\dt-sionna-rt\twingate\out\a15_pc3_fullv2.err"

$proc = Start-Process -FilePath "python" `
  -ArgumentList "-u", "A15_tx_position_refinement.py", "--full", "--device", "pc3" `
  -WorkingDirectory "C:\Users\sahil\dt-sionna-rt\twingate" `
  -RedirectStandardOutput $log -RedirectStandardError $err `
  -WindowStyle Hidden -PassThru

Write-Host "pc3 launched — PID $($proc.Id) → $log"
