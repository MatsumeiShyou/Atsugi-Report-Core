import pandas as pd
import os
import sys

# 既存のロジックからマッピングを取得するため
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))
from aggregate_report import ITEM_TO_CATEGORY

def extract():
    print("未登録品名の抽出と自動推測を開始します...")
    # 生データの読み込み
    raw_path = r'Artifacts/仕入日報問合せ.csv'
    if not os.path.exists(raw_path):
        print(f"Error: {raw_path} が見つかりません。")
        return
    
    # cp932を使用
    df_raw = pd.read_csv(raw_path, encoding='cp932', engine='python')
    # 全角スペースを除去してカラム名を正規化
    df_raw = df_raw.rename(columns=lambda x: str(x).replace('\u3000', '').strip())
    
    # 事務員版の読み込み
    human_path = r'Artifacts/厚木事業所_入荷日報_search.xlsx'
    df_hum = pd.DataFrame()
    if os.path.exists(human_path):
        try:
            # 8-8J シートを読む
            df_hum = pd.read_excel(human_path, sheet_name='8-8J')
            # 1行目をカラムにする
            df_hum.columns = df_hum.iloc[0]
            df_hum = df_hum[1:].reset_index(drop=True)
        except Exception as e:
            print(f"Warning: 事務員版の読み込みに失敗しました。推測は行われません。({e})")
            
    # 事務員版から 品名 -> 大分類 の辞書を作る (簡易的)
    human_guess_map = {}
    if not df_hum.empty and '品名' in df_hum.columns and '管理会社' in df_hum.columns:
        current_macro_category = ""
        for _, row in df_hum.iterrows():
            col0 = str(row.get('管理会社', '')).strip()
            item = str(row.get('品名', '')).strip()
            # ①段ボール などの大分類行を検出
            if col0.startswith(('①', '②', '③', '④', '⑤', '⑥')):
                current_macro_category = col0
            if item and item != 'nan' and current_macro_category:
                if item not in human_guess_map:
                    human_guess_map[item] = current_macro_category
                    
    # 生データから未登録品名を抽出
    missing_items = set()
    for _, row in df_raw.iterrows():
        item_name = str(row.get('品名', '')).strip()
        if not item_name or item_name == 'nan':
            continue
        # マッピングされているかチェック
        mapped = False
        for k in ITEM_TO_CATEGORY.keys():
            if k in item_name or item_name in k:
                mapped = True
                break
        if not mapped:
            missing_items.add(item_name)
            
    # 出力データの構築
    output_rows = []
    for item in sorted(list(missing_items)):
        guess = human_guess_map.get(item, "")
        output_rows.append({
            "得意先名": "",
            "品名": item,
            "大品目分類": guess,
            "経路分類": "",
            "備考": "推測結果を元に確認してください"
        })
        
    df_out = pd.DataFrame(output_rows)
    out_path = 'Artifacts/追加候補リスト.csv'
    df_out.to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f"抽出完了: {len(output_rows)}件の未登録品名を {out_path} に出力しました。")
    print("人間はこれをExcelで開き、正しい行を user_mappings.csv にコピペしてください。")

if __name__ == "__main__":
    extract()
