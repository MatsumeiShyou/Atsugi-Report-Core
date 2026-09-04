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
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        return list(reader)

macro_path, micro_path = get_files()
macro_rows = parse_csv(macro_path)
micro_rows = parse_csv(micro_path)

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
for i, row in enumerate(micro_rows):
    if not row: continue
    # For micro, we use Client (B col), Item (D col), Route (E col) to create a unique key
    if len(row) > 1:
        client = row[1].strip()
        if client and client not in ["客先名称", ""]:
            item = row[3].strip() if len(row) > 3 else ""
            route = row[4].strip() if len(row) > 4 else ""
            key = f"{client}_{item}_{route}"
            
            # handle exact duplicates if they appear
            original_key = key
            counter = 1
            while key in micro_map:
                key = f"{original_key}_{counter}"
                counter += 1
            
            micro_map[key] = i + 1

with open('src/mapping_definitions.py', 'w', encoding='utf-8') as f:
    f.write('from typing import Dict\n\n')
    f.write('MACRO_ROW_MAP: Dict[str, int] = ' + json.dumps(macro_map, ensure_ascii=False, indent=4) + '\n\n')
    f.write('MICRO_ROW_MAP: Dict[str, int] = ' + json.dumps(micro_map, ensure_ascii=False, indent=4) + '\n')
