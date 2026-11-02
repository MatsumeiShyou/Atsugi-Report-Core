"""入荷の予測の計算。通信はしない（AG-0015）"""
import datetime
import os
import sys
from typing import Dict, List

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from forecast import (
    Forecast, build_forecast, day_type, is_special_period, FORECAST_CATEGORIES, DISPLAY_CATEGORIES, OWN_CATEGORIES,
)


def _series(start: str, end: str, level: Dict[str, float], category: str = "①段ボール") -> pd.DataFrame:
    """日の種類ごとの一定量（平日・土・日祝）を毎日1件ずつ並べた入荷"""
    rows: List[dict] = []
    for ts in pd.date_range(start, end):
        rows.append({"transaction_date": ts.strftime("%Y-%m-%d"), "大品目分類": category,
                     "実重量": level[day_type(ts.date())]})
    return pd.DataFrame(rows)


LEVEL = {"平日": 1000.0, "土": 500.0, "日祝": 100.0}


def test_day_type_treats_holiday_as_sunday() -> None:
    assert day_type(datetime.date(2026, 11, 2)) == "平日"      # 月曜
    assert day_type(datetime.date(2026, 11, 3)) == "日祝"      # 火曜だが文化の日
    assert day_type(datetime.date(2026, 11, 7)) == "土"
    assert day_type(datetime.date(2026, 11, 8)) == "日祝"      # 日曜


def test_special_period_boundaries() -> None:
    for d in [(12, 28), (12, 31), (1, 1), (1, 4), (8, 12), (8, 16)]:
        assert is_special_period(datetime.date(2026, *d))
    for d in [(12, 27), (1, 5), (8, 11), (8, 17), (11, 3)]:
        assert not is_special_period(datetime.date(2026, *d))


def test_forecast_uses_mean_of_same_day_type_over_recent_13_weeks() -> None:
    df = _series("2026-07-01", "2026-11-01", LEVEL)
    fc = build_forecast(df, 2026, 11, today=datetime.date(2026, 11, 2))
    assert fc is not None and fc.start == datetime.date(2026, 11, 2)
    cat = fc.daily["①段ボール"]
    assert cat[1] == 1000.0      # 11/2 月曜（平日）
    assert cat[2] == 100.0       # 11/3 火曜だが祝日（文化の日）は日曜と同じ
    assert cat[6] == 500.0       # 11/7 土曜
    assert cat[7] == 100.0       # 11/8 日曜
    assert set(cat) == set(range(1, 30)), "月末（30日）まで。実績のある1日は含めない"


def test_forecast_follows_recent_level_not_old_level() -> None:
    """直近13週より前の量は使わない"""
    old = _series("2026-01-01", "2026-07-31", {"平日": 9000.0, "土": 9000.0, "日祝": 9000.0})
    recent = _series("2026-08-01", "2026-11-01", LEVEL)
    fc = build_forecast(pd.concat([old, recent]), 2026, 11, today=datetime.date(2026, 11, 2))
    assert fc is not None and fc.daily["①段ボール"][1] == 1000.0


def test_forecast_starts_from_today_even_if_today_has_partial_data() -> None:
    """今日はまだ途中なので、今日の実績が一部あっても予測の対象にする"""
    df = _series("2026-07-01", "2026-11-02", LEVEL)
    fc = build_forecast(df, 2026, 11, today=datetime.date(2026, 11, 2))
    assert fc is not None and fc.start == datetime.date(2026, 11, 2)


def test_forecast_covers_days_missing_from_data_when_data_lags() -> None:
    """計量データの更新が遅れていて、昨日までのデータが無ければ、その日も予測する"""
    df = _series("2026-07-01", "2026-10-30", LEVEL)
    fc = build_forecast(df, 2026, 11, today=datetime.date(2026, 11, 3))
    assert fc is not None and fc.start == datetime.date(2026, 11, 1)    # 月の初日から（10/31 は前月なので出さない）
    assert 0 in fc.daily["①段ボール"]


def test_forecast_is_none_when_month_is_finished() -> None:
    df = _series("2026-07-01", "2026-10-31", LEVEL)
    assert build_forecast(df, 2026, 10, today=datetime.date(2026, 11, 1)) is None
    assert build_forecast(df, 2026, 10, today=datetime.date(2026, 11, 20)) is None


def test_forecast_is_none_without_enough_history() -> None:
    df = _series("2026-10-01", "2026-11-01", LEVEL)    # 約1か月分しかない
    assert build_forecast(df, 2026, 11, today=datetime.date(2026, 11, 2)) is None
    assert build_forecast(pd.DataFrame(), 2026, 11, today=datetime.date(2026, 11, 2)) is None


def test_special_period_uses_same_day_last_year() -> None:
    last_year = pd.DataFrame([{"transaction_date": "2025-12-30", "大品目分類": "①段ボール", "実重量": 77770.0}])
    df = pd.concat([last_year, _series("2025-12-31", "2026-12-14", LEVEL)])
    fc = build_forecast(df, 2026, 12, today=datetime.date(2026, 12, 15))
    assert fc is not None
    assert fc.daily["①段ボール"][29] == 77770.0        # 12/30 は前年の12/30の実績
    assert fc.daily["①段ボール"][19] != 77770.0        # 12/20 は通常の方式


def test_special_period_falls_back_when_last_year_is_not_available() -> None:
    df = _series("2026-08-01", "2026-12-14", LEVEL)    # 前年のデータが無い
    fc = build_forecast(df, 2026, 12, today=datetime.date(2026, 12, 15))
    assert fc is not None and fc.daily["①段ボール"][29] == 1000.0     # 12/30（水曜）は通常の平日の量


def test_forecast_computes_all_categories_and_total_is_their_sum() -> None:
    parts = [_series("2026-07-01", "2026-11-01", LEVEL, c) for c in FORECAST_CATEGORIES]
    fc = build_forecast(pd.concat(parts), 2026, 11, today=datetime.date(2026, 11, 2))
    assert fc is not None and set(fc.daily) == set(FORECAST_CATEGORIES)
    assert fc.total(OWN_CATEGORIES)[1] == 5000.0
    assert fc.total(FORECAST_CATEGORIES)[1] == 6000.0
    assert set(DISPLAY_CATEGORIES) == {"①段ボール", "②新聞", "③雑誌", "⑤その他"}, "プラ類と横持ちは表示しない"


def test_forecast_is_rounded_to_10kg() -> None:
    df = _series("2026-07-01", "2026-11-01", {"平日": 1004.0, "土": 500.0, "日祝": 100.0})
    fc = build_forecast(df, 2026, 11, today=datetime.date(2026, 11, 2))
    assert fc is not None and fc.daily["①段ボール"][1] == 1000.0


def test_forecast_value_is_a_namedtuple() -> None:
    assert Forecast(start=datetime.date(2026, 11, 2), daily={}).total(["①段ボール"]) == {}
