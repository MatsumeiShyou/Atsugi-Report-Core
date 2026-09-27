import pytest
import pandas as pd
import sys
sys.path.insert(0, 'src')
from aggregate_report import transform_raw_data, build_micro_report, _filter_month

def test_totals_match():
    df_raw = pd.read_csv('Artifacts/仕入日報問合せ.csv', encoding='cp932', low_memory=False)
    df_in, df_out = transform_raw_data(df_raw)
    if "年月日" in df_in.columns:
        df_in["transaction_date"] = df_in["年月日"]
    
    for month in [8, 9]:
        micro_report = build_micro_report(df_in, df_out, 2026, month)
        
        # 元データの合計
        df_in_filtered = _filter_month(df_in, 2026, month)
        expected_total = df_in_filtered['実重量'].sum() if not df_in_filtered.empty else 0
        
        # レポートから '入荷総合計' を探す
        report_total = 0
        for row in micro_report:
            if len(row) > 1 and str(row[1]) == '入荷総合計':
                try:
                    report_total = float(str(row[-1]).replace(',', ''))
                except:
                    pass
        
        assert report_total == expected_total, f'{month}月: レポート={report_total}, 生データ={expected_total}'

