import os
import sys
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from aggregate_report import (
    transform_raw_data, build_macro_report, build_micro_report,
    is_outbound_transaction, classify_outbound_route
)

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
    
    df_inbound, df_outbound = transform_raw_data(df)
    
    assert df_inbound.loc[0, "実重量"] == 900
    assert df_inbound.loc[1, "横持フラグ"] == True
    assert df_inbound.loc[3, "経路分類"] == "プレス品"
    
    macro = build_macro_report(df_inbound, df_outbound, target_year=2026, target_month=9)
    
    # マクロレポートで青木商店を探す
    found_macro_aoki = False
    for row in macro:
        if row[0] == "" and row[1] == "青木商店":
            # 当月(2026-09)はインデックス14 (Col 14)
            assert row[14] == "900"
            found_macro_aoki = True
            break
    assert found_macro_aoki
    
    micro = build_micro_report(df_inbound, df_outbound, target_year=2026, target_month=9)
    
    # ミクロレポートで青木商店を探す（Directive 1: 品名が保持されること）
    found_micro_aoki = False
    for row in micro:
        if len(row) > 36 and row[1] == "青木商店" and row[4] == "持込":
            assert row[3] == "段ボール", f"Expected 品名 '段ボール', got '{row[3]}'"
            # Day 1 は F列 (index 5)
            assert row[5] == "900"
            # 行合計は AK列 (index 36)
            assert row[36] == "900"
            found_micro_aoki = True
            break
    assert found_micro_aoki

def test_split_pipeline_and_shipping_classification() -> None:
    """入出荷の物理分離と出荷ルート（輸出/国内）判定の検証"""
    data = {
        "仕入先名": ["青木商店", "", ""],
        "得意先名": ["", "JOP", "日本製紙（吉永工場"],
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
    jop_row = df_outbound[df_outbound["client_name"] == "JOP"].iloc[0]
    assert jop_row["経路分類"] == "1.輸出"
    
    np_row = df_outbound[df_outbound["client_name"].str.contains("日本製紙")].iloc[0]
    assert np_row["経路分類"] == "2.国内"

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
        if row[1] == "JOP" and row[3] == "古段(プレス)":
            # Day 5 は index 9 (4 + 5)
            assert row[9] == "20,000"
            assert row[36] == "20,000"
            jop_found = True
        if row[1] is not None and "日本製紙" in str(row[1]) and row[3] == "古段(プレス)":
            # Day 10 は index 14 (4 + 10)
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

