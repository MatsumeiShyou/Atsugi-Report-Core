import sys
import os
import pandas as pd
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from aggregate_report import transform_raw_data, build_macro_report, build_micro_report

def test_transform_and_coordinate_mapping() -> None:
    data = {
        "仕入先名": ["青木商店", "謎の業者", "富士営業所(横持)", "タチオカ商会", "アイダスト"],
        "品名": ["段ボール", "新聞", "雑誌", "段ボール(プレス)", "謎のゴミ"],
        "取引区分": ["引取", "持込", "引取", "引取", "持込"],
        "自社他社区分": ["自社", "自社", "他社", "他社", "他社"],
        "正味重量": [1000, 500, 2000, 3000, 100],
        "調整重量": [-100, 0, 50, -500, 0]
    }
    df = pd.DataFrame(data)
    
    # T1: Transform raw data
    transformed = transform_raw_data(df)
    
    # Verify weights
    assert transformed.loc[0, "実重量"] == 900
    
    # Verify categories and routing
    assert transformed.loc[2, "横持フラグ"] == True
    assert transformed.loc[2, "経路分類"] == "横持品"
    assert transformed.loc[0, "集計用仕入先名"] == "青木商店"
    assert transformed.loc[1, "集計用仕入先名"] == "そのた"
    
    # T2: Build macro report (coordinate mapping)
    macro = build_macro_report(transformed)
    
    # MACRO_ROW_MAP = {"①段ボール_自社回収_青木商店": 2}
    assert macro[2][0] == "青木商店"
    assert macro[2][2] == 900.0
    
    # MACRO_ROW_MAP = {"⑤その他_持込み_そのた": 168}
    assert macro[168][0] == "そのた"
    assert macro[168][1] == "謎のゴミ"
    assert macro[168][2] == 100.0
    
    # Micro report (8-5)
    micro = build_micro_report(transformed)
    # MICRO_ROW_MAP = {"青木商店": 5}
    assert micro[5][5] == 900.0
    assert micro[5][36] == 900.0
