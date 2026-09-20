import pandas as pd
import os
import re

CSV_PATH = r"Artifacts/マッピング判定用_推測付き.csv"
TARGET_FILE = r"src/aggregate_report.py"

def main():
    if not os.path.exists(CSV_PATH):
        print(f"エラー: {CSV_PATH} が見つかりません。")
        return

    # CSVの読み込み
    try:
        df = pd.read_csv(CSV_PATH)
    except Exception as e:
        print(f"CSV読み込みエラー: {e}")
        return

    # 空欄でない「判定」列を取得
    df_valid = df[df["判定（分類名または除外）"].notna() & (df["判定（分類名または除外）"] != "")]
    
    new_categories = {}
    new_ignores = set()

    for _, row in df_valid.iterrows():
        item = str(row["品名"]).strip()
        cat = str(row["判定（分類名または除外）"]).strip()
        
        if cat == "除外":
            new_ignores.add(item)
        elif cat in ["①段ボール", "②新聞", "③雑誌", "④プラ類", "⑤その他", "＜参考＞事業所間横持ち"]:
            new_categories[item] = cat
        else:
            print(f"警告: 不明なカテゴリ '{cat}' (品名: {item}) はスキップされました。")

    if not new_categories and not new_ignores:
        print("追加・更新するマッピングがありませんでした。")
        return

    # aggregate_report.py の読み込み
    with open(TARGET_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. ITEM_TO_CATEGORY の更新
    if new_categories:
        # ITEM_TO_CATEGORY の定義ブロックを探す
        pattern = r"(ITEM_TO_CATEGORY\s*=\s*\{)(.*?)(\n\})"
        match = re.search(pattern, content, re.DOTALL)
        if match:
            existing_dict_str = match.group(2)
            
            # 追加分の文字列を作成
            add_str = ""
            for item, cat in new_categories.items():
                if f'"{item}"' not in existing_dict_str and f"'{item}'" not in existing_dict_str:
                    add_str += f',\n    "{item}": "{cat}"'
            
            if add_str:
                # 最後の要素の後にカンマを追加して結合
                new_dict_str = existing_dict_str + add_str
                content = content[:match.start(2)] + new_dict_str + content[match.end(2):]
                print(f"{len(new_categories)}件の品目を ITEM_TO_CATEGORY に追加しました。")

    # 2. 除外キーワードの更新
    if new_ignores:
        pattern = r'(str\.contains\(")(.*?)(")'
        matches = list(re.finditer(pattern, content))
        # 運搬|取扱|手数料... が含まれる行を特定
        for match in matches:
            if "運搬" in match.group(2) and "手数料" in match.group(2):
                existing_kws = match.group(2).split('|')
                added_count = 0
                for item in new_ignores:
                    # すでに含まれていないかチェック
                    if not any(k in item for k in existing_kws) and item not in existing_kws:
                        existing_kws.append(item)
                        added_count += 1
                
                if added_count > 0:
                    new_kws_str = "|".join(existing_kws)
                    content = content[:match.start(2)] + new_kws_str + content[match.end(2):]
                    print(f"{added_count}件のキーワードを除外リストに追加しました。")
                break

    # 保存
    with open(TARGET_FILE, 'w', encoding='utf-8') as f:
        f.write(content)

    print("aggregate_report.py の更新が完了しました！")

if __name__ == '__main__':
    main()
