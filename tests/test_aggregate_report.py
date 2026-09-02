import sys
import os
import pandas as pd
from typing import Any

# srcディレクトリをPYTHONPATHに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from aggregate_report import process_dataframe

def test_process_dataframe() -> None:
    data = {
        "仕入先名": ["青木商店", "謎の業者", "富士営業所(横持)", "タチオカ商会", "アイダスト"],
        "品名": ["段ボール", "新聞", "雑誌", "段ボール(プレス)", "謎のゴミ"],
        "取引区分": ["引取", "持込", "引取", "引取", "持込"],
        "自社他社区分": ["自社", "自社", "他社", "他社", "他社"],
        "正味重量": [1000, 500, 2000, 3000, 100],
        "調整重量": [-100, 0, 50, -500, 0]
    }
    df = pd.DataFrame(data)
    
    result = process_dataframe(df)
    
    # 1. 実重量の計算 (マイナスの調整重量により合算値が減算されるレコード)
    assert result.loc[0, "実重量"] == 900
    assert result.loc[3, "実重量"] == 2500
    
    # 2. 横持ち拠点のレコード (状態・経路から除外されること)
    assert result.loc[2, "横持フラグ"] == True
    assert result.loc[2, "経路分類"] == "横持品"
    
    # 3. 主要顧客とそれ以外のレコード (後者が「そのた」に置換されること)
    assert result.loc[0, "仕入先名"] == "青木商店"
    assert result.loc[1, "仕入先名"] == "そのた"
    assert result.loc[2, "仕入先名"] == "そのた" # MAJOR_CLIENTSにないため置換される
    
    # 4. プレス品のレコード（経路分類が行われないこと）
    assert result.loc[3, "状態分類"] == "プレス品"
    assert result.loc[3, "経路分類"] == "-"
    
    # 5. その他の検証
    assert result.loc[0, "大品目分類"] == "①段ボール"
    assert result.loc[0, "経路分類"] == "自社回収"
    assert result.loc[4, "大品目分類"] == "⑤その他"
    assert result.loc[4, "元品名"] == "謎のゴミ"
