import pytest
import pandas as pd
import sys
sys.path.insert(0, 'src')
from aggregate_report import transform_raw_data

def test_pickup_supplier_name():
    df_mock = pd.DataFrame([
        {
            '日付': '2026/08/01',
            '伝票番号': '1001',
            '経路分類': '自社回収',
            '仕入先名': '富士ロジ厚木金田(ポジティブ)',
            '支払先名': '(合)ポジティブ',
            '運送店名': '',
            '正味重量': 1000,
            '大品目分類': '①段ボール'
        }
    ])
    df_in, _ = transform_raw_data(df_mock)
    normalized = df_in.iloc[0]['normalized_parent']
    assert 'ポジティブ' in normalized, f'Expected ポジティブ in {normalized}'

