import json
import ast
import re

with open('src/mapping_definitions.py', 'r', encoding='utf-8') as f:
    content = f.read()
    
micro_match = re.search(r'MICRO_ROW_MAP: Dict\[str, int\] = (\{.*?\})', content, re.DOTALL)
if micro_match:
    micro_dict = ast.literal_eval(micro_match.group(1))
    with open('micro_keys.txt', 'w', encoding='utf-8') as out:
        for k in list(micro_dict.keys())[:30]:
            out.write(k + '\n')
