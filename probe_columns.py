import pandas as pd
m1 = pd.read_csv('op1_measurements.csv', nrows=3)
m2 = pd.read_csv('op2_measurements.csv', nrows=3)
print("=== op1_measurements.csv columns ===")
for c in m1.columns:
    print(f"  {c}: {m1[c].tolist()}")
print()
print("=== op2_measurements.csv columns ===")
for c in m2.columns:
    print(f"  {c}: {m2[c].tolist()}")
