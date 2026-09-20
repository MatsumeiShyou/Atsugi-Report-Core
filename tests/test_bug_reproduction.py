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
    
    df_inbound, _ = transform_raw_data(df)
    
    # 経路分類は「持込み」になるはず
    assert df_inbound.loc[0, "経路分類"] == "持込み", f"Expected '持込み', got {df_inbound.loc[0, '経路分類']}"


def test_macro_p_column_is_diff_not_total() -> None:
    """P列が「13ヶ月合計」ではなく「前年同月差分」になっていることを検証する。

    テストデータ:
    - 青木商店が13ヶ月分の段ボール持込データを持つ
    - 1番目の月(2025-05): 100kg
    - 2番目〜12番目の月: 各200kg
    - 13番目の月(2026-05): 300kg

    期待値:
    - 青木商店のP列 = 300 - 100 = 200（差分）
    - 13ヶ月合計 = 100 + 200*11 + 300 = 2600 ← これは間違い
    """
    from aggregate_report import build_macro_report

    rows = []
    months = [
        ("2025-05-15", 100),   # 前年同月: 100kg
        ("2025-06-15", 200),
        ("2025-07-15", 200),
        ("2025-08-15", 200),
        ("2025-09-15", 200),
        ("2025-10-15", 200),
        ("2025-11-15", 200),
        ("2025-12-15", 200),
        ("2026-01-15", 200),
        ("2026-02-15", 200),
        ("2026-03-15", 200),
        ("2026-04-15", 200),
        ("2026-05-15", 300),   # 当月: 300kg
    ]
    for date_str, weight in months:
        rows.append({
            "仕入先名": "青木商店",
            "品名": "段ボール",
            "取引区分": "持込",
            "自社他社区分": "",
            "得意先名": "",
            "正味重量": weight,
            "調整重量": 0,
            "transaction_date": date_str,
            "支払先名": "青木商店",
            "運送店名": "",
            "備考": "",
        })

    df = pd.DataFrame(rows)
    df_inbound, df_outbound = transform_raw_data(df)
    macro = build_macro_report(df_inbound, df_outbound, target_year=2026, target_month=5)

    # ヘッダー行のP列が「前年同月差分」であること
    header = macro[0]
    assert header[15] == "前年同月差分", f"P列ヘッダーが '{header[15]}' になっている"

    # 青木商店の明細行を探す
    for row in macro:
        if row[1] == "青木商店":
            p_val = row[15]
            # P列は差分 = 300 - 100 = 200 であるべき
            assert p_val == "200", (
                f"青木商店のP列が '{p_val}' になっている。"
                f"期待値は '200'（差分: 300 - 100）"
            )
            break
    else:
        assert False, "青木商店の行が見つからない"

    # 小計行のP列も差分の合算であること
    for row in macro:
        if row[1] is not None and "合計" in str(row[1]):
            p_subtotal = row[15]
            assert p_subtotal == "200", (
                f"小計行のP列が '{p_subtotal}' になっている。"
                f"期待値は '200'（差分の合算）"
            )
            break

def test_sonota_category_preserves_supplier_name() -> None:
    from aggregate_report import transform_raw_data
    import pandas as pd
    data = {
        "仕入先名": ["A社", "B社"],
        "品名": ["ウエス", "牛乳パック"],
        "取引区分": ["持込", "持込"],
        "自社他社区分": ["", ""],
        "得意先名": ["", ""],
        "正味重量": [100, 200],
        "調整重量": [0, 0],
        "transaction_date": ["2026-09-01", "2026-09-01"],
    }
    df = pd.DataFrame(data)
    df_inbound, _ = transform_raw_data(df)
    assert df_inbound.loc[0, "store_name"] == "A社"
    assert df_inbound.loc[1, "store_name"] == "B社"

def test_plastic_press_not_lost() -> None:
    from aggregate_report import transform_raw_data
    import pandas as pd
    data = {
        "仕入先名": ["A社"],
        "品名": ["廃プラ軟質(プレス)"],
        "取引区分": ["持込"],
        "自社他社区分": [""],
        "得意先名": [""],
        "正味重量": [100],
        "調整重量": [0],
        "transaction_date": ["2026-09-01"],
    }
    df = pd.DataFrame(data)
    df_inbound, _ = transform_raw_data(df)
    assert df_inbound.loc[0, "経路分類"] == "プレス品"

def test_hybrid_adjustment_logic() -> None:
    import pandas as pd
    from aggregate_report import transform_raw_data
    data = {
        "仕入先名": ["A社", "C社"],
        "品名": ["値引き", "マイナス分"],
        "備考": ["段ボールの分", ""],
        "取引区分": ["持込", "持込"],
        "自社他社区分": ["", ""],
        "得意先名": ["", ""],
        "正味重量": [-100, -300],
        "調整重量": [0, 0],
        "transaction_date": ["2026-09-01", "2026-09-01"],
    }
    df = pd.DataFrame(data)
    df_inbound, _ = transform_raw_data(df)
    # 案3: 備考欄に「段ボール」とあるため、品名が「値引き」でも①段ボールになるべき
    assert df_inbound.loc[0, "大品目分類"] == "①段ボール"
    # 救済不可: 備考欄もなく事前登録もない場合は安全に⑤その他になるべき
    assert df_inbound.loc[1, "大品目分類"] == "⑤その他"


def test_zero_net_weight_freight_filtering():
    """
    U-NET等の月末運賃・補助金精算伝票（正味重量=0、調整重量>0）は非物理伝票として
    集計から除外されなければならない（二重計上防止）。
    一方、正当な水分・品質控除（正味=0, 調整<0）や現品入荷（正味>0）は保持されること。
    """
    from aggregate_report import transform_raw_data
    import pandas as pd
    df = pd.DataFrame([
        {'仕入先名': '(株)U-NET', '支払先名': '(株)U-NET', '品名': '段ボール', '正味重量': '0', '調整重量': '81,410', '取引区分': '持込'},
        {'仕入先名': 'B社', '支払先名': 'B社', '品名': '段ボール', '正味重量': '0', '調整重量': '-210', '取引区分': '持込'},
        {'仕入先名': 'C社', '支払先名': 'C社', '品名': '段ボール', '正味重量': '500', '調整重量': '0', '取引区分': '持込'}
    ])
    df_inbound, _ = transform_raw_data(df)
    # U-NET伝票が除外され、B社（控除）とC社（現品）の2件のみ残ること
    assert len(df_inbound) == 2
    assert "(株)U-NET" not in df_inbound["store_name"].values
    assert df_inbound.loc[df_inbound["store_name"] == "B社", "実重量"].iloc[0] == -210.0
    assert df_inbound.loc[df_inbound["store_name"] == "C社", "実重量"].iloc[0] == 500.0





def test_transform_raw_data_empty_df_crash() -> None:
    """
    Directive 2 BUG_LOOP:
    transform_raw_data に空の DataFrame を渡した際、KeyError: '仕入先名' 等で
    クラッシュせず、(空df, 空df) が安全に返却されることを検証するバグ再現テスト。
    """
    from aggregate_report import transform_raw_data
    df_empty = pd.DataFrame()
    df_in, df_out = transform_raw_data(df_empty)
    assert df_in.empty
    assert df_out.empty


def test_export_classification_tsubonoya():
    """
    BUG_LOOP: Verify that '(株)坪野谷紙業貿易部' is correctly classified as Export (1.輸出).
    Currently it falls back to '2.国内' because it's missing from the keywords.
    """
    from aggregate_report import classify_outbound_route
    import pandas as pd
    
    # Simulate a row for outbound transaction
    row = pd.Series({
        "得意先名": "(株)坪野谷紙業貿易部",
        "品名": "段ボールプレス",
        "備考": "",
        "取引区分": "出荷"
    })
    
    route = classify_outbound_route(row)
    assert route == "1.輸出", f"Expected '1.輸出', but got {route}"
