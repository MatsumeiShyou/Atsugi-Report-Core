import os
import sys
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from aggregate_report import transform_raw_data

def test_mochikomi_bug():
    """
    タチオカ商会のように、自社他社区分が「他社」であっても
    取引区分が「持込」であれば「持込み」として判定されなければならない。
    """
    data = {
        "仕入先名": ["㈲タチオカ商会"],
        "品名": ["段ボール"],
        "得意先名": [""],
        "自社他社区分": ["他社"],
        "取引区分": ["持込"],
        "正味重量": [1000],
        "調整重量": [0],
        "transaction_date": ["2026-09-01"]
    }
    df = pd.DataFrame(data)
    
    transformed = transform_raw_data(df)
    
    # 経路分類は「持込み」になるはずだが、現行ロジックでは「他社回収」になってしまう
    assert transformed.loc[0, "経路分類"] == "持込み", f"Expected '持込み', got {transformed.loc[0, '経路分類']}"
