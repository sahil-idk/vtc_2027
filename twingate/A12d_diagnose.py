import pandas as pd, numpy as np
from scipy.stats import linregress, spearmanr

df = pd.read_csv('out/pc1_full_sionna.csv')
valid = df[df['sionna_power_raw'] > -100].copy()
train_df = valid[valid['new_split'] == 'train']
val_df   = valid[valid['new_split'] == 'val']

ALPHA_CLIP = (0.0, 2.0); MIN_ROWS = 3

coefs = {}
for cell, tr in train_df.groupby('cell_id'):
    va = val_df[val_df['cell_id'] == cell]
    if len(tr) < MIN_ROWS or len(va) < MIN_ROWS:
        continue
    x, y = tr['sionna_power_raw'].values, tr['measured_rsrp'].values
    if x.std() < 1e-6:
        alpha, b = 0.0, float(y.mean())
    else:
        sl, ic, _, _, _ = linregress(x, y)
        alpha = float(np.clip(sl, *ALPHA_CLIP))
        b = float(ic)
    coefs[cell] = {'b': b, 'alpha': alpha}

rows = []
for cell, va in val_df.groupby('cell_id'):
    if cell not in coefs:
        continue
    b, alpha = coefs[cell]['b'], coefs[cell]['alpha']
    pred  = b + alpha * va['sionna_power_raw'].values
    resid = va['measured_rsrp'].values - pred
    for r in resid:
        rows.append({'cell_id': cell, 'residual': float(r), 'abs_res': abs(float(r))})

ols = pd.DataFrame(rows)
print("Residual percentiles:")
for p in [50, 75, 90, 95, 99]:
    print(f"  p{p}: {np.percentile(ols['abs_res'], p):.1f} dB")

print()
print("Top 10 worst-MAE towers:")
tw = ols.groupby('cell_id')['abs_res'].agg(['mean', 'max', 'count']).sort_values('mean', ascending=False)
print(tw.head(10).to_string())

print()
print("Coefs + sionna range for worst towers:")
for cell in tw.head(5).index:
    c = coefs.get(cell, {})
    tr_g = train_df[train_df['cell_id'] == cell]
    va_g = val_df[val_df['cell_id'] == cell]
    rho, _ = spearmanr(va_g['sionna_power_raw'], va_g['measured_rsrp'])
    print(f"  Tower {int(cell)}: alpha={c.get('alpha',0):.3f}  b={c.get('b',0):.1f}  "
          f"train_sionna_std={tr_g['sionna_power_raw'].std():.2f}  val_rho={rho:.3f}")
    print(f"    train sionna [{tr_g['sionna_power_raw'].min():.1f}, {tr_g['sionna_power_raw'].max():.1f}]  "
          f"val sionna [{va_g['sionna_power_raw'].min():.1f}, {va_g['sionna_power_raw'].max():.1f}]")

# How many rows have abs_residual > 20 dB?
big = ols[ols['abs_res'] > 20]
print(f"\nRows with |residual| > 20 dB: {len(big)} ({100*len(big)/len(ols):.1f}%)")
print(f"Their contribution to MSE: {(big['residual']**2).sum() / (ols['residual']**2).sum():.1%} of total")
print(f"\nMAE excluding >20 dB outliers: {ols[ols['abs_res']<=20]['abs_res'].mean():.3f} dB")
print(f"MAE excluding >10 dB outliers: {ols[ols['abs_res']<=10]['abs_res'].mean():.3f} dB (n={len(ols[ols['abs_res']<=10])})")
