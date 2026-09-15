"""
Full data funnel: raw cellular_dataframe_cleaned.csv -> sionna_raw.csv -> A10 split
"""
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT  = Path(__file__).parent / "out"

# ── Stage 0: Raw cellular dataframe ──────────────────────────────────────────
raw = pd.read_csv(ROOT / "cellular_dataframe_cleaned.csv", low_memory=False)
print("=" * 65)
print("STAGE 0: Raw cellular_dataframe_cleaned.csv")
print("=" * 65)
print(f"  Total rows : {len(raw):,}")
# Infer operator from device column
if 'operator' in raw.columns:
    print(f"  By operator:")
    print(raw.groupby('operator').size().to_string())
elif 'device' in raw.columns:
    op_map = {'pc1':1,'pc4':1,'pc2':2,'pc3':2}
    raw['_op'] = raw['device'].map(op_map)
    print("  By operator (inferred from device):")
    print(raw.groupby('_op').size().to_string())
print()

# ── Stage 1: After gap classification (gap_labels.csv) ───────────────────────
gl = pd.read_csv(OUT / "gap_labels.csv")
print("=" * 65)
print("STAGE 1: After gap classification (A01) -> gap_labels.csv")
print("=" * 65)
print(f"  Total rows : {len(gl):,}")
print(f"\n  By operator and gap_type:")
print(gl.groupby(['operator','gap_type']).size().to_string())
print(f"\n  By gap_type (overall):")
print(gl['gap_type'].value_counts().to_string())
print()

# ── Stage 2: After temporal split (split_index.csv) ──────────────────────────
si = pd.read_csv(OUT / "split_index.csv")
merged_si = gl.merge(si[['_row','split']], on='_row', how='left')
print("=" * 65)
print("STAGE 2: After temporal split (A02) -> train=Jun22-23 / val=Jun24")
print("=" * 65)
print(f"  Total rows : {len(merged_si):,}")
print(f"\n  By operator / split / gap_type:")
print(merged_si.groupby(['operator','split','gap_type']).size().to_string())
print()

# ── Stage 3: sionna_raw.csv (rows where Sionna computed predictions) ──────────
sr = pd.read_csv(OUT / "sionna_raw.csv")
sr_gl = sr.merge(gl[['_row','gap_type']], on='_row', how='left', suffixes=('_sr','_gl'))
gap_col = 'gap_type_gl' if 'gap_type_gl' in sr_gl.columns else 'gap_type'
print("=" * 65)
print("STAGE 3: Sionna RT predictions (A03) -> sionna_raw.csv")
print("  [Only rows within scene bounds with valid tower assignment]")
print("=" * 65)
print(f"  Total rows : {len(sr):,}  (dropped {len(gl)-len(sr):,} rows = no Sionna coverage)")
print(f"\n  By operator / split (temporal):")
print(sr.groupby(['operator','split']).size().to_string())
print(f"\n  Gap type breakdown in sionna_raw:")
print(sr_gl[gap_col].value_counts().to_string())
print()

# ── Stage 4: A10 clean dataset (Unflagged only, new random split) ─────────────
new_split = pd.read_csv(OUT / "new_split_index.csv")
sr_clean = sr_gl[sr_gl[gap_col] == 'Unflagged'].copy()
sr_a10 = sr_clean.merge(new_split, on='_row', how='inner')
print("=" * 65)
print("STAGE 4: A10 clean dataset (Unflagged only, random session split)")
print("  [TypeB + Ambiguous removed from BOTH train and val]")
print("=" * 65)
print(f"  Total rows : {len(sr_a10):,}  (dropped {len(sr)-len(sr_a10):,} flagged from sionna_raw)")
print(f"\n  By operator / new_split:")
print(sr_a10.groupby(['operator','new_split']).size().to_string())
print(f"\n  By device / new_split:")
print(sr_a10.groupby(['device','new_split']).size().to_string())
print()

# ── Summary funnel ────────────────────────────────────────────────────────────
print("=" * 65)
print("FUNNEL SUMMARY")
print("=" * 65)
print(f"  Raw dataset                     : {len(raw):>8,} rows")
print(f"  After gap labelling (A01)       : {len(gl):>8,} rows  (same, labels added)")
print(f"  -- Unflagged                    : {(gl['gap_type']=='Unflagged').sum():>8,}")
print(f"  -- TypeA (instrumentation fail) : {(gl['gap_type']=='TypeA').sum():>8,}")
print(f"  -- TypeB (signal dropout)       : {(gl['gap_type']=='TypeB').sum():>8,}")
print(f"  -- Ambiguous                    : {(gl['gap_type']=='Ambiguous').sum():>8,}")
print(f"  After Sionna coverage filter    : {len(sr):>8,} rows  (scene bounds + tower match)")
print(f"  -- of which flagged in Sionna   : {len(sr)-len(sr_clean):>8,}  (TypeB={( sr_gl[gap_col]=='TypeB').sum()}, Amb={(sr_gl[gap_col]=='Ambiguous').sum()})")
print(f"  Final clean (Unflagged only)    : {len(sr_a10):>8,} rows")
print(f"  -- Train (new random split)     : {(sr_a10['new_split']=='train').sum():>8,}")
print(f"  -- Val   (new random split)     : {(sr_a10['new_split']=='val').sum():>8,}")
print()
op1_train = len(sr_a10[(sr_a10['operator']==1)&(sr_a10['new_split']=='train')])
op1_val   = len(sr_a10[(sr_a10['operator']==1)&(sr_a10['new_split']=='val')])
op2_train = len(sr_a10[(sr_a10['operator']==2)&(sr_a10['new_split']=='train')])
op2_val   = len(sr_a10[(sr_a10['operator']==2)&(sr_a10['new_split']=='val')])
print(f"  Op1: train={op1_train:,}  val={op1_val:,}")
print(f"  Op2: train={op2_train:,}  val={op2_val:,}")
