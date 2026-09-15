"""A14 — Final Gate-2 aggregated results across all four devices."""
import json
import numpy as np

results = {}
file_map = {'pc1': 'pc1_full_results.json', 'pc2': 'pc2_results.json',
            'pc3': 'pc3_results.json',      'pc4': 'pc4_results.json'}
for dev in ['pc1', 'pc4', 'pc2', 'pc3']:
    with open(f'out/{file_map[dev]}') as f:
        r = json.load(f)
    # normalise key name across scripts
    if 'mae_per_tower_ols_combined' in r and 'mae_per_tower_ols' not in r:
        r['mae_per_tower_ols'] = r['mae_per_tower_ols_combined']
    results[dev] = r

print('=' * 72)
print('GATE-2 RESULTS  --  Per-tower OLS + Sionna RT  (stratified 80/20 split)')
print('=' * 72)
hdr = f"  {'Device':<6} {'Op':<4} {'Towers':>7} {'Val rows':>9} {'Global off':>11} {'Tower mean':>11} {'OLS+Sionna':>11} {'Gain':>7}"
print(hdr)
print('  ' + '-' * 68)
for dev in ['pc1', 'pc4', 'pc2', 'pc3']:
    r = results[dev]
    n_tw = r['n_towers_ols'] + r['n_towers_fallback']
    gain = r['mae_per_tower_mean'] - r['mae_per_tower_ols']
    line = (f"  {dev:<6} {r['operator']:<4} {n_tw:>7} {r['n_val']:>9,} "
            f"{r['mae_global_offset']:>11.3f} {r['mae_per_tower_mean']:>11.3f} "
            f"{r['mae_per_tower_ols']:>11.3f} {gain:>+7.3f}")
    print(line)

print()
print('  Operator-level weighted average (by val rows):')
for op_name, devs in [('Op1 (Telekom)', ['pc1', 'pc4']),
                      ('Op2 (Vodafone)', ['pc2', 'pc3'])]:
    n_vals  = [results[d]['n_val'] for d in devs]
    total_n = sum(n_vals)
    w_ols  = sum(results[d]['mae_per_tower_ols']  * results[d]['n_val'] for d in devs) / total_n
    w_mean = sum(results[d]['mae_per_tower_mean'] * results[d]['n_val'] for d in devs) / total_n
    w_goff = sum(results[d]['mae_global_offset']  * results[d]['n_val'] for d in devs) / total_n
    gain   = w_mean - w_ols
    print(f'    {op_name:<20}  n={total_n:,}  global={w_goff:.3f}  tower_mean={w_mean:.3f}  OLS+Sionna={w_ols:.3f}  gain={gain:+.3f} dB')

print()
print('  Per-device Spearman rho (Sionna spatial vs measured RSRP, val):')
for dev in ['pc1', 'pc4', 'pc2', 'pc3']:
    r = results[dev]
    print(f'    {dev}: rho_median={r["spearman_rho_median"]:.3f}  '
          f'alpha_mean={r["alpha_mean"]:.3f}  '
          f'OLS_towers={r["n_towers_ols"]}  fallback={r["n_towers_fallback"]}')

# Save combined results
combined = {
    'per_device': results,
    'per_operator': {}
}
for op_name, devs in [('op1', ['pc1', 'pc4']), ('op2', ['pc2', 'pc3'])]:
    n_vals  = [results[d]['n_val'] for d in devs]
    total_n = sum(n_vals)
    combined['per_operator'][op_name] = {
        'devices': devs,
        'n_val': total_n,
        'mae_global_offset':   sum(results[d]['mae_global_offset']  * results[d]['n_val'] for d in devs) / total_n,
        'mae_per_tower_mean':  sum(results[d]['mae_per_tower_mean'] * results[d]['n_val'] for d in devs) / total_n,
        'mae_per_tower_ols':   sum(results[d]['mae_per_tower_ols']  * results[d]['n_val'] for d in devs) / total_n,
    }
    combined['per_operator'][op_name]['gain_vs_mean'] = (
        combined['per_operator'][op_name]['mae_per_tower_mean'] -
        combined['per_operator'][op_name]['mae_per_tower_ols']
    )

with open('out/gate2_final_results.json', 'w') as f:
    json.dump(combined, f, indent=2)
print('\nSaved: out/gate2_final_results.json')
