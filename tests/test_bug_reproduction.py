import pytest
import pandas as pd
import sys
import numpy as np
import os
sys.path.insert(0, 'src')
from aggregate_report import transform_raw_data, _filter_month

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

def test_bug_reproduction_jimuin_totals():
    """
    ユーザーからの指摘「スプレッドシートに出力される数字がおかしい。事務員さんのものとやはり違う」に対する再現テスト。
    """
    csv_path = os.path.join('Artifacts', '仕入日報問合せ.csv')
    if not os.path.exists(csv_path):
        pytest.skip(f"{csv_path} is missing")

    df_raw = pd.read_csv(csv_path, encoding='cp932', low_memory=False)
    df_in, df_out = transform_raw_data(df_raw)

    if "年月日" in df_in.columns:
        df_in["transaction_date"] = df_in["年月日"]
    df_in_filtered = _filter_month(df_in, 2026, 8)

    # 事務員の正しい合計値
    expected_totals = {
        18: 90450,
        19: 58450,
        21: 71120,
        28: 68370,
        31: 56670
    }

    errors = []
    for day, expected in expected_totals.items():
        actual = df_in_filtered[df_in_filtered['_day'] == day]['実重量'].sum()
        if not np.isclose(actual, expected):
            errors.append(f"Day {day}: Expected {expected}, got {actual}")

    assert not errors, "\n".join(errors)


# --- 事務員の集計表（入荷日報2023.xlsx）との照合で判明した分類ルールの再現テスト ---
# 期待値は、2024/09〜2026/08 の生データ伝票を事務員の日次シートと照合して得たもの（人間承認済み）。
from aggregate_report import prepare_raw_data


def _inbound(rows: list) -> pd.DataFrame:
    base = {"年月日": "2026/08/03", "取引区分": "引取", "自社他社区分": "他社", "運送店名": None,
            "正味重量": 1000, "調整重量": 0, "デ区": "仕入"}
    df_in, _ = transform_raw_data(prepare_raw_data(pd.DataFrame([{**base, **r} for r in rows])))
    return df_in.set_index("仕入先名")


def test_collection_route_follows_carrier_not_jisha_tasha_flag():
    """引取の自社回収/他社回収は運送店名で決まる（空欄・U-NET=自社、それ以外=他社）。自社他社区分は使わない"""
    df = _inbound([
        {"仕入先名": "客先A", "品名": "段ボールバラ", "自社他社区分": "他社", "運送店名": None},
        {"仕入先名": "客先B", "品名": "段ボールバラ", "自社他社区分": "他社", "運送店名": "㈱Ｕ－ＮＥＴ(自社)"},
        {"仕入先名": "客先C", "品名": "段ボールバラ", "自社他社区分": "自社", "運送店名": "鏡紙業"},
    ])
    assert df.loc["客先A", "経路分類"] == "自社回収"
    assert df.loc["客先B", "経路分類"] == "自社回収"
    assert df.loc["客先C", "経路分類"] == "他社回収"


def test_pet_bottle_is_other_category():
    """ペットボトルは事務員の集計表では「その他」"""
    df = _inbound([{"仕入先名": "客先A", "品名": "ペットボトル"}])
    assert df.loc["客先A", "大品目分類"] == "⑤その他"


def test_cloth_items_are_other_category():
    """布類・ウエスは「その他」（事務員の集計表に古布・繊維の区分は無い）"""
    df = _inbound([
        {"仕入先名": "客先A", "品名": "布類", "取引区分": "持込"},
        {"仕入先名": "客先B", "品名": "ウエス", "取引区分": "持込"},
    ])
    assert df.loc["客先A", "大品目分類"] == "⑤その他"
    assert df.loc["客先B", "大品目分類"] == "⑤その他"


def test_newspaper_pickup_is_other_category():
    """新聞の引取は「その他」へ（集計表に新聞の回収欄が無い）。持込は「新聞」のまま"""
    df = _inbound([
        {"仕入先名": "客先A", "品名": "新聞バラ", "取引区分": "引取"},
        {"仕入先名": "客先B", "品名": "新聞バラ", "取引区分": "持込"},
    ])
    assert df.loc["客先A", "大品目分類"] == "⑤その他"
    assert df.loc["客先B", "大品目分類"] == "②新聞"


def test_purchase_adjustment_slip_adds_no_weight():
    """仕入調整伝票（正味0・調整重量のみ）は計上しない。事務員は正味重量だけを集計している"""
    df = _inbound([
        {"仕入先名": "客先A", "品名": "段ボールバラ", "正味重量": 1000},
        {"仕入先名": "客先B", "品名": "段ボールバラ", "正味重量": 0, "調整重量": 980, "デ区": "仕入調整"},
    ])
    assert df["実重量"].sum() == 1000


def test_temporary_item_code_9999_is_excluded():
    """商品コード9999（商品マスタに無い臨時品目: 燃えくず・燃殻・産廃・空カゴ運搬など）は入出荷とも計上しない（AG-0005）"""
    base = {"年月日": "2026/08/03", "取引区分": "持込", "正味重量": 1000, "調整重量": 0}
    rows = [
        {**base, "得意先名": "(横持)本社事業所", "品名": "燃えくず", "商品コード": 9999},
        {**base, "得意先名": "(横持)本社事業所", "品名": "アルミ缶プレス", "商品コード": 4402},
        {**base, "仕入先名": "客先A", "品名": "宮崎から空カゴ", "商品コード": 9999},
        {**base, "仕入先名": "客先B", "品名": "段ボールバラ", "商品コード": 1000},
    ]
    df_in, df_out = transform_raw_data(prepare_raw_data(pd.DataFrame(rows)))
    assert df_out["品名"].tolist() == ["アルミ缶プレス"]
    assert df_in["品名"].tolist() == ["段ボールバラ"]


def test_kanko_count_variants_are_aggregated_as_one_item():
    """山櫻の紙管は入力時に品名へ概算本数を書き足す（紙管　80本 等）が、事務員は本数に関係なく「紙管」1行で集計する"""
    df = _inbound([
        {"仕入先名": "山櫻A", "品名": "紙管　80本", "正味重量": 190},
        {"仕入先名": "山櫻B", "品名": "紙管　130本", "正味重量": 240},
    ])
    assert df["品名"].tolist() == ["紙管", "紙管"]
    assert set(df["大品目分類"]) == {"⑤その他"}


def test_kanko_count_slip_is_listed_with_specific_reason():
    """紙管(本) は正味重量欄に本数が入った本数伝票。計上せず、除外一覧では重量と誤読されない理由を付ける"""
    from aggregate_report import transform_with_excluded
    base = {"年月日": "2026/08/03", "仕入先名": "山櫻", "取引区分": "引取", "調整重量": 0}
    rows = [{**base, "品名": "紙管(本)", "正味重量": 80}, {**base, "品名": "紙管　80本", "正味重量": 190}]
    df_in, _, excluded = transform_with_excluded(prepare_raw_data(pd.DataFrame(rows)))
    assert df_in["実重量"].tolist() == [190]
    assert excluded["除外理由"].tolist() == ["紙管の本数伝票（重量は別伝票で計上）"]


def _select_target_csv_files(monkeypatch):
    """google_api は import 時に .env（本番のSupabase接続情報）を読むため、テストでは読ませない"""
    import importlib
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.delitem(sys.modules, "google_api", raising=False)
    return importlib.import_module("google_api").select_target_csv_files


def test_only_daily_auto_saved_csvs_are_read(monkeypatch):
    """Driveには手動DLの重複ファイル（仕入日報問合せ2026_08.csv 等）も置かれる。
    毎日自動保存される 仕入日報問合せ.csv / 出荷日報問合せ.csv だけを読み、同名が複数あれば最新を使う"""
    select_target_csv_files = _select_target_csv_files(monkeypatch)
    items = [
        {"id": "a", "name": "出荷日報問合せ.csv", "modifiedTime": "2026-10-05T15:00:00Z"},
        {"id": "b", "name": "仕入日報問合せ.csv", "modifiedTime": "2026-10-04T15:00:00Z"},
        {"id": "c", "name": "仕入日報問合せ.csv", "modifiedTime": "2026-10-05T15:00:00Z"},
        {"id": "d", "name": "仕入日報問合せ2026_08.csv", "modifiedTime": "2026-10-01T00:00:00Z"},
        {"id": "e", "name": "仕入日報問合せ20260801_0815.csv", "modifiedTime": "2026-10-01T00:00:00Z"},
        {"id": "f", "name": "出荷日報問合せ20261002.csv", "modifiedTime": "2026-10-02T00:00:00Z"},
    ]
    assert sorted(item["id"] for item in select_target_csv_files(items)) == ["a", "c"]


def test_missing_daily_csv_stops_the_run(monkeypatch):
    """入荷・出荷どちらかの自動保存CSVが無ければ、不完全な表を書かないよう停止する"""
    select_target_csv_files = _select_target_csv_files(monkeypatch)
    with pytest.raises(ValueError, match="出荷日報問合せ.csv"):
        select_target_csv_files([{"id": "b", "name": "仕入日報問合せ.csv", "modifiedTime": "2026-10-05T15:00:00Z"}])


def test_shipping_items_categorized_like_clerk(caplog):
    """出荷の未登録品名は事務員の計上先に合わせる: 塩ビ・フレコン=プラ類、ティーエスエンバイロの残紙=新聞、
    その他の残紙・カップ色トリム・ビニール重袋・白アート=その他（未登録の警告も出さない）"""
    import logging
    base = {"年月日": "2026/09/03", "取引区分": "持込", "正味重量": 1000, "調整重量": 0}
    rows = [
        {**base, "得意先名": "和円商事", "品名": "塩ビ"},
        {**base, "得意先名": "和円商事", "品名": "フレコンプレス"},
        {**base, "得意先名": "ﾃｨｰｴｽｴﾝﾊﾞｲﾛ", "品名": "残紙"},
        {**base, "得意先名": "㈱岩本商店", "品名": "残紙"},
        {**base, "得意先名": "日誠産業", "品名": "カップ色トリムプレス"},
        {**base, "得意先名": "大王製紙", "品名": "ビニール重袋プレス"},
        {**base, "得意先名": "王子ﾏﾃﾘｱ㈱富士", "品名": "白アートプレス"},
    ]
    with caplog.at_level(logging.WARNING, logger="aggregate_report"):
        _, df_out = transform_raw_data(prepare_raw_data(pd.DataFrame(rows)))
    got = dict(zip(df_out["得意先名"] + "/" + df_out["品名"], df_out["大品目分類"]))
    assert got == {
        "和円商事/塩ビ": "④プラ類",
        "和円商事/フレコンプレス": "④プラ類",
        "ティーエスエンバイロ/残紙": "②新聞",
        "(株)岩本商店/残紙": "⑤その他",
        "日誠産業/カップ色トリムプレス": "⑤その他",
        "大王製紙/ビニール重袋プレス": "⑤その他",
        "王子マテリア(株)富士/白アートプレス": "⑤その他",
    }
    unknown = [r.getMessage() for r in caplog.records if "Unknown item mapped" in r.getMessage()]
    assert not [m for m in unknown if any(row["品名"] in m for row in rows)], unknown


def test_supabase_rule_master_does_not_change_results(monkeypatch):
    """AG-0007: 除外ルールはコードとテストだけで持つ。Supabase の rule_master（BLACK/WHITE）は読まない。
    本番の rule_master は BLACK「神奈中商事」で通常入荷を落とし、WHITE「山櫻」で紙管の本数伝票を救っていた"""
    import supabase_client
    monkeypatch.setattr(supabase_client, "fetch_rule_master",
                        lambda: {"BLACK": ["神奈中商事"], "WHITE": ["山櫻"]}, raising=False)
    df = _inbound([
        {"仕入先名": "(株)神奈中商事", "品名": "段ボールバラ", "取引区分": "持込", "正味重量": 1000},
        {"仕入先名": "(株)山櫻八王子の森工場", "品名": "紙管(本)", "正味重量": 80},
    ])
    assert df.index.tolist() == ["(株)神奈中商事"]
    assert df["実重量"].sum() == 1000
