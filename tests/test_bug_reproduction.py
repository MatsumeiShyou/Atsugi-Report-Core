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
    transformed = transform_raw_data(df)
    macro = build_macro_report(transformed)

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
    transformed = transform_raw_data(df)
    assert transformed.loc[0, "仕入先名"] == "A社"
    assert transformed.loc[1, "仕入先名"] == "B社"

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
    transformed = transform_raw_data(df)
    assert transformed.loc[0, "経路分類"] == "持込み"

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
    transformed = transform_raw_data(df)
    # 案3: 備考欄に「段ボール」とあるため、品名が「値引き」でも①段ボールになるべき
    assert transformed.loc[0, "大品目分類"] == "①段ボール"
    # 救済不可: 備考欄もなく事前登録もない場合は安全に⑤その他になるべき
    assert transformed.loc[1, "大品目分類"] == "⑤その他"
