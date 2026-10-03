"""
AG-0003: raw_nyuka_data（Supabase）へのDB往復を廃止した際に、DBが暗黙に行っていた
列の正規化・ホワイトリスト・型変換を prepare_raw_data が再現していることを固定するテスト。
期待値は、2026-10-04 に観測した本番DBの列定義と返却値の型にもとづく。
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from aggregate_report import prepare_raw_data, transform_raw_data, RAW_COLUMNS


def _inbound_csv_like() -> pd.DataFrame:
    # 実CSV同様、ヘッダーに全角空白を含み、DBに存在しない列（ﾔｰﾄﾞｺｰﾄﾞ, デ区）も含む
    return pd.DataFrame({
        "年月日": ["2026/08/01", "2026/08/02"],
        "車番": [1234, 5678],
        "仕入先名": ["青木商店", np.nan],
        "品　　名": ["段ボール", "新聞"],
        "正味重量": [1000, 2000],
        "調整重量": [np.nan, -10],
        "単　価": [12.5, np.nan],
        "取引区分": ["持込", "引取"],
        "ﾔｰﾄﾞｺｰﾄﾞ": [27, 99],
        "デ区": ["仕入", "仕入"],
    })


def test_columns_are_whitelisted_and_completed() -> None:
    out = prepare_raw_data(_inbound_csv_like())
    assert list(out.columns) == RAW_COLUMNS
    # 旧DBに列が無かったため変換処理へ渡らなかった列は、引き続き渡さない
    assert "ﾔｰﾄﾞｺｰﾄﾞ" not in out.columns
    assert "デ区" not in out.columns
    # CSVに無い列は None（旧DBの NULL 相当）
    assert out["得意先名"].isna().all()


def test_types_match_old_db_roundtrip() -> None:
    out = prepare_raw_data(_inbound_csv_like())
    # date 型 → 'YYYY-MM-DD' 文字列
    assert out["transaction_date"].tolist() == ["2026-08-01", "2026-08-02"]
    # text 型 → 数値も文字列化される
    assert out["車番"].tolist() == ["1234", "5678"]
    # 欠損は None/NaN（旧DBの NULL）。"nan" という文字列にならないこと
    assert out.loc[1, "仕入先名"] is None or pd.isna(out.loc[1, "仕入先名"])
    assert out.loc[0, "品名"] == "段ボール"
    # numeric 型
    assert out.loc[1, "調整重量"] == -10
    assert out.loc[0, "単価"] == 12.5


def test_sales_columns_are_merged() -> None:
    sales = pd.DataFrame({
        "出荷日付": ["2026/08/05"],
        "得意先名": ["坪野谷紙業貿易部"],
        "商品名(売上)": ["古段(プレス)"],
        "正味重量(売上)": [20000],
        "取引区分名称(売上)": ["売上"],
    })
    out = prepare_raw_data(sales)
    assert out.loc[0, "transaction_date"] == "2026-08-05"
    assert out.loc[0, "品名"] == "古段(プレス)"
    assert out.loc[0, "正味重量"] == 20000
    assert out.loc[0, "取引区分"] == "売上"

    _, df_out = transform_raw_data(out)
    assert len(df_out) == 1
    assert df_out.iloc[0]["経路分類"] == "1.輸出"


def test_unparseable_date_fails_fast() -> None:
    # 旧DBでは date 型へのINSERTが失敗して処理全体が止まっていた。黙って欠損にしない
    df = pd.DataFrame({"年月日": ["2026/08/01", "日付不明"], "品名": ["a", "b"]})
    with pytest.raises(ValueError):
        prepare_raw_data(df)
