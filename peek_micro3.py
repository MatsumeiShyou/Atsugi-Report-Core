import csv
import json
import os

micro_path = None
for f in os.listdir('Artifacts'):
    path = os.path.join('Artifacts', f)
    if os.path.isfile(path) and os.path.getsize(path) > 50000:
        micro_path = path

data = []
with open(micro_path, 'r', encoding='utf-8') as f:
    reader = csv.reader(f)
    for i, row in enumerate(reader):
        if i >= 50: break
        data.append(row)

with open('scratch_micro_50.json', 'w', encoding='utf-8') as out:
    json.dump(data, out, ensure_ascii=False, indent=2)
