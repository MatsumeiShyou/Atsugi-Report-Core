import os
import csv
import json

def get_files():
    macro_path = None
    micro_path = None
    for f in os.listdir('Artifacts'):
        path = os.path.join('Artifacts', f)
        if os.path.isfile(path):
            if os.path.getsize(path) < 50000:
                macro_path = path
            else:
                micro_path = path
    return macro_path, micro_path

def parse_csv(path):
    for enc in ['utf-8-sig', 'utf-8', 'cp932', 'shift_jis']:
        try:
            with open(path, 'r', encoding=enc) as f:
                reader = csv.reader(f)
                rows = list(reader)
                # If we get here and there are no replacement characters , it's good.
                text = "".join(r[0] for r in rows if r)
                if '' not in text and '繝' not in text and '①' in text:
                    return rows, enc
        except Exception:
            pass
    
    # fallback
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.reader(f)
        return list(reader), 'utf-8'

macro_path, micro_path = get_files()
macro_rows, macro_enc = parse_csv(macro_path)
micro_rows, micro_enc = parse_csv(micro_path)

print(f"Macro encoding: {macro_enc}")
print(f"Micro encoding: {micro_enc}")

macro_map = {}
current_cat = ""
current_route = ""
for i, row in enumerate(macro_rows):
    if not row: continue
    val = row[0].strip()
    if not val: continue
    
    if any(val.startswith(c) for c in ["①", "②", "③", "④", "⑤"]):
        current_cat = val
        macro_map[val] = i + 1
        continue
    
    if ("持込" in val or "引取" in val) and "計" not in val:
        current_route = val
        macro_map[f"{current_cat}_{current_route}_HEADER"] = i + 1
        continue
        
    if "横持" in val and "計" not in val:
        current_cat = "横持品"
        current_route = ""
        macro_map[val] = i + 1
        continue
        
    key = f"{current_cat}_{current_route}_{val}" if current_route else f"{current_cat}_{val}"
    macro_map[key] = i + 1

micro_map = {}
current_header = ""
for i, row in enumerate(micro_rows):
    if not row: continue
    val = row[0].strip()
    if not val: continue
    
    if val not in micro_map:
        micro_map[val] = i + 1
    else:
        micro_map[f"{val}_{i+1}"] = i + 1

with open('src/mapping_definitions.py', 'w', encoding='utf-8') as f:
    f.write('from typing import Dict\n\n')
    f.write('MACRO_ROW_MAP: Dict[str, int] = ' + json.dumps(macro_map, ensure_ascii=False, indent=4) + '\n\n')
    f.write('MICRO_ROW_MAP: Dict[str, int] = ' + json.dumps(micro_map, ensure_ascii=False, indent=4) + '\n')
