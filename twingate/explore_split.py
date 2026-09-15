import pandas as pd
import numpy as np

gl = pd.read_csv('out/gap_labels.csv')
si = pd.read_csv('out/split_index.csv')
sr = pd.read_csv('out/sionna_raw.csv')

sr_full = sr.merge(gl[['_row','Latitude','Longitude','gap_type']], on='_row', how='left', suffixes=('_sr','_gl'))
sr_full = sr_full.merge(si[['_row','measurement']], on='_row', how='left')
# gap_type_sr is from sionna_raw, gap_type_gl is from gap_labels (authoritative)
gap_col = 'gap_type_gl' if 'gap_type_gl' in sr_full.columns else 'gap_type'

print("=== Are TypeA/B rows in sionna_raw? ===")
print(sr_full[gap_col].value_counts().to_string())
print()

print("=== Sessions in sionna_raw by device ===")
print(sr_full.groupby(['operator','device'])['measurement'].nunique().to_string())
print()

print("=== GPS bounds ===")
print("Lat:", sr_full['Latitude'].min(), "to", sr_full['Latitude'].max())
print("Lon:", sr_full['Longitude'].min(), "to", sr_full['Longitude'].max())
print()

print("=== Per-session row counts in sionna_raw (train vs val) ===")
grp = sr_full.groupby(['device','measurement','split']).size().unstack(fill_value=0)
print(grp.to_string())
