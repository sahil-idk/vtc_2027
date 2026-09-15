import pandas as pd
df = pd.read_csv('out/pc3_full_sionna.csv')
print(f'pc3 checkpoint: {len(df):,} rows, {df["cell_id"].nunique()} towers done')
print(f'new_split counts: {df["new_split"].value_counts().to_dict()}')
