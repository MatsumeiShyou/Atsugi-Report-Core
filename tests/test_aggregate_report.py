import os
import sys
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from aggregate_report import transform_raw_data, build_macro_report, build_micro_report, _find_macro_idx, _find_micro_idx

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
    
    idx_aoki = _find_macro_idx("青木商店", "①段ボール", "持込み", False)
    assert idx_aoki != -1
    # macro は 14列。インデックスはC列が0。日付指定がないのですべて0列目に入るはず。
    assert macro[idx_aoki - 1][0] == 900.0
    
    idx_sonota = _find_macro_idx("そのた", "③雑誌", "持込み", False)
    if idx_sonota != -1:
        assert macro[idx_sonota - 1][0] == 2050.0
        
    micro = build_micro_report(transformed)
    
    idx_aoki_micro = _find_micro_idx("青木商店", "①段ボール", "持込み")
    assert idx_aoki_micro != -1
    
    # A~E列の属性テキストの検証
    assert micro[idx_aoki_micro - 1][1] == "青木商店" # B列
    assert micro[idx_aoki_micro - 1][3] == "段ボール" # D列
    assert micro[idx_aoki_micro - 1][4] == "持込み"    # E列
    
    # 日付から算出したインデックスの検証 (Day 1はindex 5)
    assert micro[idx_aoki_micro - 1][5] == 900.0
    # 行合計はindex 36
    assert micro[idx_aoki_micro - 1][36] == 900.0
