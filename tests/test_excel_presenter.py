import os
import sys
import datetime
import openpyxl
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from excel_presenter import ExcelReportPresenter

TEMPLATE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../Artifacts/厚木事業所_入荷日報_search.xlsx'))

def test_category_matches_strict() -> None:
    """Directive 2: 異品目間の誤名寄せ（新聞・雑誌が段ボールに混入する問題）を防止する厳格判定"""
    presenter = ExcelReportPresenter(TEMPLATE_PATH)
    
    # 段ボール
    assert presenter._category_matches("①段ボール", "段ボール-持込み") is True
    assert presenter._category_matches("①段ボール", "段ボール-自社回収") is True
    assert presenter._category_matches("①段ボール", "新聞-バラ持込み") is False
    assert presenter._category_matches("①段ボール", "その他-持込み") is False

    # 新聞
    assert presenter._category_matches("②新聞", "新聞-バラ持込み") is True
    assert presenter._category_matches("②新聞", "段ボール-持込み") is False
    assert presenter._category_matches("②新聞", "雑誌-バラ持込み") is False

    # 雑誌
    assert presenter._category_matches("③雑誌", "雑誌-バラ持込み") is True
    assert presenter._category_matches("③雑誌", "雑誌-自社回収") is True
    assert presenter._category_matches("③雑誌", "段ボール-自社回収") is False

    # プラ類
    assert presenter._category_matches("④プラ類", "プラ-持込み") is True
    assert presenter._category_matches("④プラ類", "プラ-自社回収") is True
    assert presenter._category_matches("④プラ類", "その他-持込み") is False

    # その他
    assert presenter._category_matches("⑤その他", "その他-持込み") is True
    assert presenter._category_matches("⑤その他", "その他-自社回収") is True
    assert presenter._category_matches("⑤その他", "プラ-持込み") is False
    assert presenter._category_matches("⑤その他", "段ボール-持込み") is False

    # 事業所間横持ち
    assert presenter._category_matches("＜参考＞事業所間横持ち", "事業所間横持ち") is True
    assert presenter._category_matches("＜参考＞事業所間横持ち", "段ボール-持込み") is False


def test_small_vendor_pickup_never_drops() -> None:
    """Directive 2: 全品目・全経路で「そのた」行が捕捉され、小口引取が脱落(None)しないこと"""
    presenter = ExcelReportPresenter(TEMPLATE_PATH)
    wb = openpyxl.load_workbook(TEMPLATE_PATH, data_only=True)
    ws = wb['8-8J']
    index = presenter._index_template_rows(ws)

    # 1. 既知業者の品目境界テスト
    # 青木商店の新聞(持込)は段ボール行(Row 5)ではなく新聞行(Row 228)にマッピングされること
    row_aoki_shinbun = pd.Series({"仕入先名": "青木商店", "大品目分類": "②新聞", "経路分類": "持込"})
    assert presenter._find_inbound_row(row_aoki_shinbun, index) == 228

    # タチオカ商会の段ボール(持込)は段ボール行(Row 4)にマッピングされること
    row_tachioka = pd.Series({"仕入先名": "タチオカ商会", "大品目分類": "①段ボール", "経路分類": "持込"})
    assert presenter._find_inbound_row(row_tachioka, index) == 4

    # 2. 未知小口業者のフォールバックテスト（None にならず正しい品目のそのた行へ）
    # 新聞・持込
    unknown_shinbun_mochi = pd.Series({"仕入先名": "未知の古紙回収店", "大品目分類": "②新聞", "経路分類": "持込"})
    r_shinbun = presenter._find_inbound_row(unknown_shinbun_mochi, index)
    assert r_shinbun is not None
    assert 221 <= r_shinbun <= 251, f"新聞持込の範囲外: {r_shinbun}"

    # 雑誌・引取（Reviewer指摘の脱落バグの根絶確認）
    unknown_mag_hikitori = pd.Series({"仕入先名": "未知の小口引取先", "大品目分類": "③雑誌", "経路分類": "自社回収"})
    r_mag = presenter._find_inbound_row(unknown_mag_hikitori, index)
    assert r_mag is not None, "雑誌引取の小口データが None で脱落しています"
    assert 322 <= r_mag <= 414, f"雑誌引取の範囲外: {r_mag}"

    # プラ類・持込 / 引取
    unknown_pla_mochi = pd.Series({"仕入先名": "未知のプラ持込店", "大品目分類": "④プラ類", "経路分類": "持込"})
    assert presenter._find_inbound_row(unknown_pla_mochi, index) is not None

    unknown_pla_hiki = pd.Series({"仕入先名": "未知のプラ引取先", "大品目分類": "④プラ類", "経路分類": "自社回収"})
    assert presenter._find_inbound_row(unknown_pla_hiki, index) is not None

    # その他・持込 / 引取
    unknown_other_mochi = pd.Series({"仕入先名": "未知の金属店", "大品目分類": "⑤その他", "経路分類": "持込"})
    assert presenter._find_inbound_row(unknown_other_mochi, index) is not None

    unknown_other_hiki = pd.Series({"仕入先名": "未知の他社回収店", "大品目分類": "⑤その他", "経路分類": "他社回収"})
    assert presenter._find_inbound_row(unknown_other_hiki, index) is not None


def test_stale_data_cleared_and_multi_slip_formula(tmp_path) -> None:
    """Directive 3: 前月残存データの初期化と複数伝票の加算式注入の検証"""
    presenter = ExcelReportPresenter(TEMPLATE_PATH)
    output_xlsx = str(tmp_path / "test_report_2026_09.xlsx")

    # 2026年9月のテストデータ（青木商店: 9/1に2件、9/2に1件。他社・他日は実績なし）
    df_inbound = pd.DataFrame([
        {
            "仕入先名": "青木商店", "品名": "段ボール", "大品目分類": "①段ボール", "経路分類": "持込",
            "実重量": 1330, "transaction_date": "2026-09-01", "_day": 1, "_year": 2026, "_month": 9
        },
        {
            "仕入先名": "青木商店", "品名": "段ボール", "大品目分類": "①段ボール", "経路分類": "持込",
            "実重量": 1730, "transaction_date": "2026-09-01", "_day": 1, "_year": 2026, "_month": 9
        },
        {
            "仕入先名": "青木商店", "品名": "段ボール", "大品目分類": "①段ボール", "経路分類": "持込",
            "実重量": 1500, "transaction_date": "2026-09-02", "_day": 2, "_year": 2026, "_month": 9
        }
    ])
    df_outbound = pd.DataFrame([
        {
            "client_name": "JOP", "spec_name": "古段(プレス)", "大品目分類": "①段ボール", "経路分類": "1.輸出",
            "実重量": 21000, "transaction_date": "2026-09-05", "_day": 5, "_year": 2026, "_month": 9
        }
    ])

    presenter.render_monthly_report(
        df_inbound=df_inbound,
        df_outbound=df_outbound,
        target_year=2026,
        target_month=9,
        output_path=output_xlsx
    )

    wb = openpyxl.load_workbook(output_xlsx, data_only=False)
    ws = wb["8-8J"]

    # 青木商店の段ボール行 (Row 5) の検証
    # Day 1 (Col F / 6): 複数伝票なので '=1330+1730' の数式であること
    cell_day1 = ws.cell(row=5, column=6)
    assert cell_day1.value == "=1330+1730", f"Expected '=1330+1730', got {cell_day1.value}"

    # Day 2 (Col G / 7): 単一伝票なので数値 1500 であること
    cell_day2 = ws.cell(row=5, column=7)
    assert cell_day2.value == 1500, f"Expected 1500, got {cell_day2.value}"

    # Day 3 (Col H / 8): 実績なしセルは None（8月の旧データがクリアされていること）
    cell_day3 = ws.cell(row=5, column=8)
    assert cell_day3.value is None, f"Expected None (cleared stale data), got {cell_day3.value}"

    # タチオカ商会 (Row 4): 9月は実績なし。8月実績（500.0）が残存せず None にクリアされていること
    cell_tachioka_day1 = ws.cell(row=4, column=6)
    assert cell_tachioka_day1.value is None, f"Expected None for inactive row, got {cell_tachioka_day1.value}"

    # 段ボール持込み合計行 (Row 56): SUM数式が維持されていること
    cell_total_day1 = ws.cell(row=56, column=6)
    assert str(cell_total_day1.value).startswith("=SUM"), f"Expected =SUM formula, got {cell_total_day1.value}"

    # 出荷行 (JOP Row 753, Day 5 / Col J / 10) の検証
    cell_jop = ws.cell(row=753, column=10)
    assert cell_jop.value == 21000, f"Expected 21000 at Row 753 Col 10, got {cell_jop.value}"


def test_render_monthly_report_outbound_real_data(tmp_path) -> None:
    """Directive 3: 実データに即した出荷トランザクション（JOP等）を渡し、行753等に正しく注入されることを検証"""
    presenter = ExcelReportPresenter(TEMPLATE_PATH)
    output_xlsx = str(tmp_path / "test_report_outbound.xlsx")

    df_in = pd.DataFrame([
        {"仕入先名": "青木商店", "品名": "段ボール", "大品目分類": "①段ボール", "経路分類": "持込", "実重量": 1200, "transaction_date": "2026-08-01"}
    ])
    df_out = pd.DataFrame([
        {"client_name": "JOP", "spec_name": "古段(プレス)", "大品目分類": "①段ボール", "経路分類": "1.輸出", "実重量": 21000, "transaction_date": "2026-08-05"}
    ])
    presenter.render_monthly_report(df_in, df_out, 2026, 8, output_xlsx)

    wb = openpyxl.load_workbook(output_xlsx, data_only=False)
    ws = wb["8-8J"]
    val_jop = ws.cell(row=753, column=10).value
    assert val_jop == 21000, f"Expected 21000 at Row 753 Col 10, got {val_jop}"
