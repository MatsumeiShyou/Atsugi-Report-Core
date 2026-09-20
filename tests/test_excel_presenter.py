import os
import sys
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from excel_presenter import ExcelReportPresenter

def test_excel_presenter_new_architecture(tmp_path):
    df_inbound = pd.DataFrame([
        {
            "仕入先名": "青木商店", "normalized_parent": "青木商店", "品名": "段ボール", 
            "大品目分類": "①段ボール", "経路分類": "持込",
            "実重量": 1330, "transaction_date": "2026-09-01"
        },
        {
            "仕入先名": "青木商店", "normalized_parent": "青木商店", "品名": "段ボール", 
            "大品目分類": "①段ボール", "経路分類": "持込",
            "実重量": 1730, "transaction_date": "2026-09-01"
        },
        {
            "仕入先名": "青木商店", "normalized_parent": "青木商店", "品名": "段ボール", 
            "大品目分類": "①段ボール", "経路分類": "持込",
            "実重量": 1500, "transaction_date": "2026-09-02"
        }
    ])
    
    df_outbound = pd.DataFrame([
        {
            "client_name": "JOP", "得意先名": "JOP", "spec_name": "古段(プレス)", "品名": "古段(プレス)",
            "大品目分類": "①段ボール", "経路分類": "1.輸出",
            "実重量": 21000, "transaction_date": "2026-09-05"
        }
    ])

    presenter = ExcelReportPresenter(template_path="dummy.xlsx")
    output_xlsx = str(tmp_path / "test_report_2026_09.xlsx")

    presenter.render_monthly_report(
        df_inbound=df_inbound,
        df_outbound=df_outbound,
        target_year=2026,
        target_month=9,
        output_path=output_xlsx
    )

    assert os.path.exists(output_xlsx)
    df_result = pd.read_excel(output_xlsx, header=None)
    
    found_aoki = False
    found_jop = False
    
    for idx, row in df_result.iterrows():
        row_str = " ".join(str(x) for x in row.values)
        if "青木商店" in row_str:
            found_aoki = True
            assert 3060 in row.values or 3060.0 in row.values
            assert 1500 in row.values or 1500.0 in row.values
        if "JOP" in row_str:
            found_jop = True
            assert 21000 in row.values or 21000.0 in row.values

    assert found_aoki
    assert found_jop
