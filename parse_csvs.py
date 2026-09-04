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

def parse_macro(path):
    map_dict = {}
    current_cat = ""
    current_route = ""
    
    with open(path, 'r', encoding='shift_jis', errors='replace') as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if not row: continue
            val = row[0].strip()
            if not val: continue
            
            if any(val.startswith(c) for c in ["①", "②", "③", "④", "⑤"]):
                current_cat = val
                map_dict[val] = i + 1
                continue
                
            if ("持込" in val or "引取" in val) and "計" not in val:
                current_route = val
                map_dict[f"{current_cat}_{current_route}_HEADER"] = i + 1
                continue
                
            if "横持" in val and "計" not in val:
                current_cat = "横持品"
                current_route = ""
                map_dict[val] = i + 1
                continue
                
            key = f"{current_cat}_{current_route}_{val}" if current_route else f"{current_cat}_{val}"
            map_dict[key] = i + 1
            
    return map_dict

def parse_micro(path):
    map_dict = {}
    current_header = ""
    
    with open(path, 'r', encoding='shift_jis', errors='replace') as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if not row: continue
            val = row[0].strip()
            if not val: continue
            
            if val not in map_dict:
                map_dict[val] = i + 1
            else:
                map_dict[f"{val}_{i+1}"] = i + 1
                
    return map_dict

macro_path, micro_path = get_files()
macro_map = parse_macro(macro_path)
micro_map = parse_micro(micro_path)

with open('src/mapping_definitions.py', 'w', encoding='utf-8') as f:
    f.write('from typing import Dict\n\n')
    f.write('MACRO_ROW_MAP: Dict[str, int] = ' + json.dumps(macro_map, ensure_ascii=False, indent=4) + '\n\n')
    f.write('MICRO_ROW_MAP: Dict[str, int] = ' + json.dumps(micro_map, ensure_ascii=False, indent=4) + '\n')
