import pandas as pd
import unicodedata
import os
import sys

CSV_PATH = r"Artifacts/仕入日報問合せ.csv"
OUTPUT_FILE = r"Artifacts/マッピング判定用_推測付き.csv"

def normalize_text(text):
    if pd.isna(text): return ""
    return unicodedata.normalize('NFKC', str(text)).strip()

def safe_numeric(val):
    try:
        return float(str(val).replace(',', ''))
    except:
        return 0.0

def guess_category(item_name):
    # 1. 除外キーワード
    ignore_kws = ["運搬", "加工賃", "手数料", "リース", "紹介料", "キャンセル"]
    if any(k in item_name for k in ignore_kws):
        return "除外"
        
    # 2. その他の推測（頻出）
    sonota_kws = ["機密", "色上", "糊", "布類", "雑袋", "荷潰し", "軟質", "アルミ", "鉄", "切茶", "パルプ", "巻取", "ペーパー"]
    if any(k in item_name for k in sonota_kws):
        return "⑤その他"
        
    return "" # 推測できない場合は空欄

def main():
    df_csv = pd.read_csv(CSV_PATH, encoding='cp932', low_memory=False)

    sys.path.insert(0, 'src')
    from aggregate_report import ITEM_TO_CATEGORY
    system_known_items = set([normalize_text(c) for c in ITEM_TO_CATEGORY.keys() if c])

    unknown_items_summary = {}

    for index, row in df_csv.iterrows():
        item_name = normalize_text(row.get("品　　名", ""))
        
        if not item_name or len(item_name) <= 1 or item_name in ['nan', '0', '0.0', 'NaT']:
            continue
            
        if any(k in item_name for k in system_known_items if k):
            continue

        net_weight = safe_numeric(row.get("正味重量", 0))
        adj_weight = safe_numeric(row.get("調整重量", 0))
        total_weight = net_weight + adj_weight

        if item_name not in unknown_items_summary:
            unknown_items_summary[item_name] = {"count": 0, "total_weight": 0.0}
            
        unknown_items_summary[item_name]["count"] += 1
        unknown_items_summary[item_name]["total_weight"] += total_weight

    data = []
    for item, stats in sorted(unknown_items_summary.items(), key=lambda x: x[1]["total_weight"], reverse=True):
        guessed = guess_category(item)
        data.append({
            "品名": item,
            "出現回数": stats["count"],
            "総重量(kg)": int(stats["total_weight"]),
            "判定（分類名または除外）": guessed
        })
        
    df_out = pd.DataFrame(data)
    df_out.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')
    print(f"判定用CSVを {OUTPUT_FILE} に出力しました。推測値アシスト付き。")

if __name__ == '__main__':
    main()
