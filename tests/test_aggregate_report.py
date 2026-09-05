import os
import sys
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from aggregate_report import transform_raw_data, build_macro_report, build_micro_report

def test_transform_and_coordinate_mapping() -> None:
    data = {
        "仕入先名": ["青木商店", "富士営業所(横持)", "そのた", "段ボール(プレス)", "アイダスト"],
        "品名": ["段ボール", "紙ゴミ", "雑誌", "段ボール(プレス)", "新聞"],
        "経路": ["持込", "自社", "持込", "持込", "他社"],
        "正味重量": [1000, 500, 2000, 3000, 100],
        "調整重量": [-100, 0, 50, -500, 0],
        "transaction_date": ["2026-09-01", "2026-09-01", "2026-09-01", "2026-09-01", "2026-09-01"]
    }
    df = pd.DataFrame(data)
    
    transformed = transform_raw_data(df)
    
    assert transformed.loc[0, "実重量"] == 900
    assert transformed.loc[1, "横持フラグ"] == True
    assert transformed.loc[3, "経路分類"] == "プレス品"
    
    macro = build_macro_report(transformed)
    
    # マクロレポートで青木商店を探す
    found_macro_aoki = False
    for row in macro:
        if row[0] == "青木商店" and row[1] == "段ボール":
            # C列 (index 2) が月別データ
            assert row[2] == 900.0
            assert row[15] == 900.0 # 行合計
            found_macro_aoki = True
            break
    assert found_macro_aoki
    
    micro = build_micro_report(transformed)
    
    # ミクロレポートで青木商店を探す
    found_micro_aoki = False
    for row in micro:
        if row[1] == "青木商店" and row[4] == "持込み":
            assert row[3] == "段ボール"
            # Day 1 は F列 (index 5)
            assert row[5] == 900.0
            # 行合計は AK列 (index 36)
            assert row[36] == 900.0
            found_micro_aoki = True
            break
    assert found_micro_aoki
