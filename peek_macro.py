import json
import ast
import re

with open('src/mapping_definitions.py', 'r', encoding='utf-8') as f:
    content = f.read()
    
macro_match = re.search(r'MACRO_ROW_MAP: Dict\[str, int\] = (\{.*?\})', content, re.DOTALL)
if macro_match:
    macro_dict = ast.literal_eval(macro_match.group(1))
    for k in list(macro_dict.keys()):
        if "プレス" in k:
            print(k)
