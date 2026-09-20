import pandas as pd
import os

def load_user_mappings(csv_path: str):
    if not os.path.exists(csv_path):
        return {}, {}
    df = pd.read_csv(csv_path, comment='#')
    item_map = {}
    client_map = {}
    # 簡単のため、今回は品名->大分類のマップと、得意先名->経路のマップだけを抽出
    for _, row in df.iterrows():
        client = str(row.get("得意先名", "")).strip()
        item = str(row.get("品名", "")).strip()
        cat = str(row.get("大品目分類", "")).strip()
        route = str(row.get("経路分類", "")).strip()
        
        if item and cat and item != 'nan':
            item_map[item] = cat
        if client and route and client != 'nan':
            client_map[client] = route
            
    return item_map, client_map
