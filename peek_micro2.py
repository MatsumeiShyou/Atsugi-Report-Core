import csv
micro_path = None
import os
for f in os.listdir('Artifacts'):
    path = os.path.join('Artifacts', f)
    if os.path.isfile(path) and os.path.getsize(path) > 50000:
        micro_path = path

with open(micro_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
    reader = csv.reader(f)
    for i, row in enumerate(reader):
        if i >= 50: break
        if row:
            print(f"{i+1}: {row[0]}")
