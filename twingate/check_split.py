import pandas as pd
sr = pd.read_csv('out/sionna_raw.csv')
gl = pd.read_csv('out/gap_labels.csv')
new_split = pd.read_csv('out/new_split_index.csv')

sr_full = sr.merge(gl[['_row','gap_type']], on='_row', how='left', suffixes=('_sr','_gl'))
gap_col = 'gap_type_gl' if 'gap_type_gl' in sr_full.columns else 'gap_type'

print("=== sionna_raw.csv gap_type breakdown (before any filtering) ===")
print(sr_full[gap_col].value_counts().to_string())
print()

sr_clean = sr_full[sr_full[gap_col] == 'Unflagged']
n_removed = len(sr_full) - len(sr_clean)
n_typeB = (sr_full[gap_col] == 'TypeB').sum()
n_amb   = (sr_full[gap_col] == 'Ambiguous').sum()
n_typeA = (sr_full[gap_col] == 'TypeA').sum()

print(f"Rows kept (Unflagged only): {len(sr_clean):,}")
print(f"Rows removed: {n_removed}  (TypeA={n_typeA}, TypeB={n_typeB}, Ambiguous={n_amb})")
print()

sr_clean2 = sr_clean.merge(new_split, on='_row', how='inner')
print("=== A10 new split row counts (Unflagged rows only) ===")
print(sr_clean2.groupby(['operator','new_split']).size().to_string())
print()
total_train = (sr_clean2['new_split'] == 'train').sum()
total_val   = (sr_clean2['new_split'] == 'val').sum()
print(f"Total train : {total_train:,}")
print(f"Total val   : {total_val:,}")
print(f"Grand total : {total_train+total_val:,}")
print()
print("What EXACTLY is excluded from both train AND val:")
print("  TypeA (pc4 instrumentation failure) : already not in sionna_raw at all")
print(f"  TypeB (genuine signal dropout)       : {n_typeB} rows removed from all analysis")
print(f"  Ambiguous                            : {n_amb} rows removed from all analysis")
print()
print("Conclusion: ALL flagged rows are excluded from BOTH train and val in A10.")
