import os
import csv
import glob

# Find files
files = os.listdir('Artifacts')
macro_file = None
micro_file = None
for f in files:
    if 'v' in f or '計' in f:
        macro_file = os.path.join('Artifacts', f)
    elif f.endswith('.csv'):
        micro_file = os.path.join('Artifacts', f)

print(f"Macro file: {macro_file}")
print(f"Micro file: {micro_file}")

# Try to read A column of macro
print("--- MACRO A COLUMN (first 50) ---")
try:
    with open(macro_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if i >= 50: break
            if row:
                print(f"Row {i+1}: {row[0]}")
except Exception as e:
    try:
        with open(macro_file, 'r', encoding='shift_jis') as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if i >= 50: break
                if row:
                    print(f"Row {i+1}: {row[0]}")
    except Exception as e2:
        print(e2)

