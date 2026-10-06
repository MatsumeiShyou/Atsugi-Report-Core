import os
import sys
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from aggregate_report import (
    transform_raw_data, build_macro_report, build_micro_report,
    is_outbound_transaction, classify_outbound_route
)

def test_split_pipeline_and_shipping_classification() -> None:
    """入出荷の物理分離と出荷ルート（輸出/国内）判定の検証"""
    data = {
        "仕入先名": ["青木商店", "", ""],
        "得意先名": ["", "坪野谷紙業貿易部", "日本製紙（吉永工場"],
        "品名": ["段ボール", "古段(プレス)", "段ボールプレス"],
        "取引区分": ["持込", "売上", "売上"],
        "デ区": ["仕入", "売上", "売上"],
        "正味重量": [1000, 20000, 15000],
        "調整重量": [0, 0, 0],
        "transaction_date": ["2026-08-01", "2026-08-01", "2026-08-01"]
    }
    df = pd.DataFrame(data)
    df_inbound, df_outbound = transform_raw_data(df)

    assert len(df_inbound) == 1
    assert df_inbound.loc[0, "store_name"] == "青木商店"

    assert len(df_outbound) == 2
    tsubonoya_row = df_outbound[df_outbound["client_name"] == "坪野谷紙業貿易部"].iloc[0]
    assert tsubonoya_row["経路分類"] == "1.輸出"
    
    nippon_row = df_outbound[df_outbound["client_name"].str.contains("日本製紙")].iloc[0]
    assert nippon_row["経路分類"] == "2.国内"

def test_directive_1_shipping_in_micro_report() -> None:
    """Directive 1: build_micro_report が df_outbound を用いて ＜出荷＞ セクションを完全生成すること"""
    data_in = [
        {'仕入先名': '青木商店', '品名': '段ボール', '取引区分': '持込', '正味重量': 1000, '調整重量': 0, 'transaction_date': '2026-08-01'}
    ]
    data_out = [
        {'得意先名': 'JOP', '品名': '古段(プレス)', '取引区分': '売上', 'デ区': '売上', '正味重量': 20000, '調整重量': 0, 'transaction_date': '2026-08-05'},
        {'得意先名': '日本製紙(吉永工場', '品名': '古段(プレス)', '取引区分': '売上', 'デ区': '売上', '正味重量': 15000, '調整重量': 0, 'transaction_date': '2026-08-10'}
    ]
    df_in = pd.DataFrame(data_in)
    df_out = pd.DataFrame(data_out)
    
    df_inbound, _ = transform_raw_data(df_in)
    _, df_outbound = transform_raw_data(df_out)
    
    micro = build_micro_report(df_inbound, df_outbound, target_year=2026, target_month=8)
    
    # ＜出荷＞ セクションの存在確認
    shipping_header_found = False
    jop_found = False
    np_found = False

    for row in micro:
        if row[0] == "＜出荷＞":
            shipping_header_found = True
        if len(row) > 36 and row[1] == "JOP" and row[3] == "古段(プレス)":
            # Day 5 は index 9 (5 + 4)
            assert row[9] == "20,000"
            assert row[36] == "20,000"
            jop_found = True
        if len(row) > 36 and row[1] is not None and "日本製紙" in str(row[1]) and row[3] == "古段(プレス)":
            # Day 10 は index 14
            assert row[14] == "15,000"
            assert row[36] == "15,000"
            np_found = True

    assert shipping_header_found, "＜出荷＞ ヘッダーが見つかりません"
    assert jop_found, "JOP の出荷行が見つかりません"
    assert np_found, "日本製紙の出荷行が見つかりません"


def test_transform_raw_data_empty_input() -> None:
    """Directive 3: 空の DataFrame を入力した際、エラーなく2つの空 DataFrame が返却されること"""
    df_empty = pd.DataFrame()
    df_in, df_out = transform_raw_data(df_empty)
    assert df_in.empty, "df_inbound should be empty"
    assert df_out.empty, "df_outbound should be empty"


def test_excluded_slips_are_returned_with_reason() -> None:
    """除外した伝票は捨てずに理由付きで返し、月次の確認用一覧に出せること"""
    from aggregate_report import transform_with_excluded, build_excluded_report, prepare_raw_data
    data = [
        {"年月日": "2026/08/03", "仕入先名": "青木商店", "品名": "段ボールバラ", "取引区分": "持込", "正味重量": 1000, "商品コード": 1000},
        {"年月日": "2026/08/05", "得意先名": "(横持)本社事業所", "品名": "燃えくず", "取引区分": "持込", "正味重量": 25650, "商品コード": 9999},
        {"年月日": "2026/08/04", "仕入先名": "ﾕｰﾈｯﾄ(山櫻運搬)", "品名": "運搬料／車", "取引区分": "引取", "正味重量": 0, "商品コード": 9800},
        {"年月日": "2026/07/31", "得意先名": "(横持)本社事業所", "品名": "燃殻", "取引区分": "持込", "正味重量": 13370, "商品コード": 9999},
    ]
    df_in, df_out, excluded = transform_with_excluded(prepare_raw_data(pd.DataFrame(data)))
    assert df_in["品名"].tolist() == ["段ボールバラ"]
    assert df_out.empty
    assert len(excluded) == 3
    reasons = dict(zip(excluded["品名"], excluded["除外理由"]))
    assert "9999" in reasons["燃えくず"]
    assert reasons["運搬料/車"]

    grid = build_excluded_report(excluded, target_year=2026, target_month=8)
    body = [row for row in grid[2:] if any(row)]
    # 対象月（8月）の2件だけが日付順に並ぶ。7月分は出さない
    assert [row[0] for row in body] == ["2026-08-04", "2026-08-05"]
    assert body[1][2] == "燃えくず" and body[1][4] == "25,650"


def test_rows_are_not_split_by_carrier() -> None:
    """AG-0006: KPI分析用に、同じ客先・品名・経路の実績は運送店名が違っても1行にまとめる（日次・計シート、入出荷とも）"""
    from aggregate_report import prepare_raw_data
    base = {"年月日": "2026/08/03", "取引区分": "引取", "調整重量": 0}
    data = [
        {**base, "仕入先名": "山櫻", "品名": "クラフト", "運送店名": "(株)U-NET", "正味重量": 100},
        {**base, "仕入先名": "山櫻", "品名": "クラフト", "運送店名": "(株)U-NET(自社)", "正味重量": 200},
        {**base, "年月日": "2026/08/04", "得意先名": "大王製紙", "品名": "新聞プレス", "取引区分": "持込", "運送店名": "A運送", "正味重量": 10000},
        {**base, "年月日": "2026/08/04", "得意先名": "大王製紙", "品名": "新聞プレス", "取引区分": "持込", "運送店名": "B運送", "正味重量": 12000},
    ]
    df_in, df_out = transform_raw_data(prepare_raw_data(pd.DataFrame(data)))

    micro = build_micro_report(df_in, df_out, target_year=2026, target_month=8)
    kraft = [r for r in micro if len(r) > 36 and r[1] == "山櫻" and r[3] == "クラフト"]
    assert len(kraft) == 1 and kraft[0][36] == "300"

    macro = build_macro_report(df_in, df_out, target_year=2026, target_month=8)
    kraft_m = [r for r in macro if r[2] == "山櫻" and r[4] == "クラフト"]
    assert len(kraft_m) == 1 and kraft_m[0][18] == "300"
    daio_m = [r for r in macro if r[2] == "大王製紙" and r[4] == "新聞プレス"]
    assert len(daio_m) == 1 and daio_m[0][18] == "22,000"
