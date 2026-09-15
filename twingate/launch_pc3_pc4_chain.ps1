# Chains: wait for pc2 → launch pc3 → wait for pc3 → launch pc4
$pc2_log = "C:\Users\sahil\dt-sionna-rt\twingate\out\a15_pc2_correct.log"
$pc2_csv = "C:\Users\sahil\dt-sionna-rt\twingate\out\pc2_refinement_results.csv"

Write-Host "$(Get-Date -Format 'HH:mm') Waiting for pc2 (Op2 scene)..."
while ($true) {
    Start-Sleep -Seconds 60
    $last = Get-Content $pc2_log -Tail 3 2>$null
    if ($last -match "Total Sionna calls") { Write-Host "$(Get-Date -Format 'HH:mm') pc2 done."; break }
    $done = if (Test-Path $pc2_csv) { (Get-Content $pc2_csv | Measure-Object -Line).Lines - 1 } else { 0 }
    Write-Host "$(Get-Date -Format 'HH:mm') pc2: $done towers done..."
}

# Launch pc3 (Op2 scene)
$log3 = "C:\Users\sahil\dt-sionna-rt\twingate\out\a15_pc3_correct.log"
$err3 = "C:\Users\sahil\dt-sionna-rt\twingate\out\a15_pc3_correct.err"
$pc3 = Start-Process -FilePath "python" `
  -ArgumentList "-u", "A15_tx_position_refinement.py", "--full", "--device", "pc3" `
  -WorkingDirectory "C:\Users\sahil\dt-sionna-rt\twingate" `
  -RedirectStandardOutput $log3 -RedirectStandardError $err3 `
  -WindowStyle Hidden -PassThru
Write-Host "$(Get-Date -Format 'HH:mm') pc3 (Op2 scene) launched — PID $($pc3.Id)"

$pc3_log = $log3
$pc3_csv = "C:\Users\sahil\dt-sionna-rt\twingate\out\pc3_refinement_results.csv"
Write-Host "$(Get-Date -Format 'HH:mm') Waiting for pc3..."
while ($true) {
    Start-Sleep -Seconds 60
    $last = Get-Content $pc3_log -Tail 3 2>$null
    if ($last -match "Total Sionna calls") { Write-Host "$(Get-Date -Format 'HH:mm') pc3 done."; break }
    $done = if (Test-Path $pc3_csv) { (Get-Content $pc3_csv | Measure-Object -Line).Lines - 1 } else { 0 }
    Write-Host "$(Get-Date -Format 'HH:mm') pc3: $done towers done..."
}

# Launch pc4 (Op1 scene)
$log4 = "C:\Users\sahil\dt-sionna-rt\twingate\out\a15_pc4_correct.log"
$err4 = "C:\Users\sahil\dt-sionna-rt\twingate\out\a15_pc4_correct.err"
$pc4 = Start-Process -FilePath "python" `
  -ArgumentList "-u", "A15_tx_position_refinement.py", "--full", "--device", "pc4" `
  -WorkingDirectory "C:\Users\sahil\dt-sionna-rt\twingate" `
  -RedirectStandardOutput $log4 -RedirectStandardError $err4 `
  -WindowStyle Hidden -PassThru
Write-Host "$(Get-Date -Format 'HH:mm') pc4 (Op1 scene) launched — PID $($pc4.Id)"
