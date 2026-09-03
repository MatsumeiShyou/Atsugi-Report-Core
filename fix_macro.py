import json

with open('src/mapping_definitions.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add "⑤その他_持込み_そのた": 168
content = content.replace('"⑤その他_持込み_湘南リユース": 165', '"⑤その他_持込み_湘南リユース": 165,\n    "⑤その他_持込み_そのた": 168')

with open('src/mapping_definitions.py', 'w', encoding='utf-8') as f:
    f.write(content)
