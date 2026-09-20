import pandas as pd
import unicodedata
import os
import sys

CSV_PATH = r"Artifacts/仕入日報問合せ.csv"
OUTPUT_FILE = r"Artifacts/マッピング不足候補リスト.md"

def normalize_text(text):
    if pd.isna(text): return ""
    return unicodedata.normalize('NFKC', str(text)).strip()

def safe_numeric(val):
    try:
        return float(str(val).replace(',', ''))
    except:
        return 0.0

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

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("# 未登録品名 抽出レポート（総重量付き）\n\n")
        f.write("本レポートは、システムが知らない「未登録の品名」を抽出し、その総重量を付記したものです。\n")
        f.write("金額調整の項目であってもシステム上は重量（架空の重量）が発生するため、総重量だけで本物の荷物か金額調整かを自動判定することはできません。\n")
        f.write("人間がこのリストを見て、「これは本物の荷物だから登録する」「これは運搬料や加工賃だから除外リストに入れる」と判断するためのアシスト資料です。\n\n")
        
        f.write("## 1. システム未登録の品名と、それによって発生している重量\n")
        
        for item, stats in sorted(unknown_items_summary.items(), key=lambda x: x[1]["total_weight"], reverse=True):
            f.write(f"- **{item}** (出現回数: {stats['count']}回, 総重量: {stats['total_weight']:,.0f} kg)\n")

    print(f"抽出完了！レポートを {OUTPUT_FILE} に出力しました。")

if __name__ == '__main__':
    main()
