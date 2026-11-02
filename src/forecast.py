"""入荷の残りの日の予測（AG-0015）。通信はしない。

方式（過去17か月のバックテストで比較して選んだ）:
  日の種類（平日／土曜／日曜・祝日）ごとに、直近13週の品目別の日量の平均を、残りの日の予測とする。
  年末年始（12/28〜1/4）とお盆（8/12〜8/16）は、前年の同じ日の実績を使う（前年のデータがあれば）。
  天気は使わない（検証したが、予測の精度はほとんど変わらなかったため）。
"""
import datetime
from typing import Dict, List, NamedTuple, Optional

import jpholiday  # type: ignore
import pandas as pd

WINDOW_DAYS = 91          # 直近13週
MIN_HISTORY_DAYS = 56     # 予測を出すために最低限必要な履歴（8週）
JST = datetime.timezone(datetime.timedelta(hours=9))

# 予測を計算する区分。入荷合計は6区分の予測の合計にする（平均は足し算できるので、合計を別に予測した場合と一致する）
FORECAST_CATEGORIES = ['①段ボール', '②新聞', '③雑誌', '④プラ類', '⑤その他', '＜参考＞事業所間横持ち']
# シートに予測を出す区分。プラ類と横持ちは誤差が約38%と大きいため出さない（入荷合計の計算には使う）
DISPLAY_CATEGORIES = ['①段ボール', '②新聞', '③雑誌', '⑤その他']
OWN_CATEGORIES = ['①段ボール', '②新聞', '③雑誌', '④プラ類', '⑤その他']  # 横持ちを除く入荷

NOTE = ("赤字は予測（直近13週の、平日・土曜・日曜祝日それぞれの平均。年末年始とお盆は前年の同じ日）。"
        "月末見込＝実績＋予測。段ボール・新聞・雑誌・その他の合計と、入荷合計の行だけに出す。予測は参考値")


class Forecast(NamedTuple):
    start: datetime.date                 # 予測を入れる最初の日
    daily: Dict[str, Dict[int, float]]   # 区分 → {日（0始まり）: kg}。FORECAST_CATEGORIES のすべて

    def total(self, categories: List[str]) -> Dict[int, float]:
        """区分を足し合わせた日ごとの予測"""
        result: Dict[int, float] = {}
        for category in categories:
            for day, kg in self.daily.get(category, {}).items():
                result[day] = result.get(day, 0.0) + kg
        return result


def day_type(day: datetime.date) -> str:
    if day.weekday() == 6 or jpholiday.is_holiday(day):
        return "日祝"
    return "土" if day.weekday() == 5 else "平日"


def is_special_period(day: datetime.date) -> bool:
    """年末年始とお盆。曜日では説明できない量になるため、前年の同じ日を使う"""
    return (day.month == 12 and day.day >= 28) or (day.month == 1 and day.day <= 4) \
        or (day.month == 8 and 12 <= day.day <= 16)


def _round10(kg: float) -> float:
    """計量の最小単位が10kgなので、10kgに丸める"""
    return float(round(kg, -1))


def build_forecast(
    df_inbound: pd.DataFrame,
    year: int,
    month: int,
    today: Optional[datetime.date] = None,
) -> Optional[Forecast]:
    """df_inbound（transaction_date・大品目分類・実重量を持つ入荷）から、対象月の残りの日の予測を作る。
    出せない場合（月が終わっている、履歴が足りない）は None。
    予測の開始日: データの最新日の翌日。ただし、今日はまだ途中なので今日以降（計量が遅れていればその分も予測する）。"""
    if df_inbound.empty or "transaction_date" not in df_inbound.columns:
        return None
    today = today or datetime.datetime.now(JST).date()
    frame = pd.DataFrame({
        "date": pd.to_datetime(df_inbound["transaction_date"], errors="coerce").dt.normalize(),
        "category": df_inbound["大品目分類"],
        "kg": pd.to_numeric(df_inbound["実重量"], errors="coerce").fillna(0.0),
    }).dropna(subset=["date"])
    if frame.empty:
        return None

    first_day = frame["date"].min().date()
    cutoff = min(frame["date"].max().date(), today - datetime.timedelta(days=1))
    month_start = datetime.date(year, month, 1)
    month_end = (pd.Period(f"{year}-{month:02d}", freq="M") + 1).to_timestamp().date() - datetime.timedelta(days=1)
    if cutoff >= month_end or (cutoff - first_day).days + 1 < MIN_HISTORY_DAYS:
        return None
    start = max(cutoff + datetime.timedelta(days=1), month_start)

    window = pd.date_range(max(first_day, cutoff - datetime.timedelta(days=WINDOW_DAYS - 1)), cutoff)  # 履歴のある日だけ
    history = pd.date_range(first_day, cutoff)
    window_types = pd.Series([day_type(d.date()) for d in window], index=window)
    forecast_days = [d.date() for d in pd.date_range(start, month_end)]

    daily: Dict[str, Dict[int, float]] = {}
    for category in FORECAST_CATEGORIES:
        series = frame[frame["category"] == category].groupby("date")["kg"].sum().reindex(history, fill_value=0.0)
        recent = series.reindex(window, fill_value=0.0)
        overall = float(recent.mean())
        by_type = {t: float(recent[window_types == t].mean()) for t in set(window_types) if (window_types == t).any()}
        values: Dict[int, float] = {}
        for day in forecast_days:
            last_year = (pd.Timestamp(day) - pd.DateOffset(years=1)).normalize()
            if is_special_period(day) and last_year in series.index:
                kg = float(series[last_year])
            else:
                kg = by_type.get(day_type(day), overall)
            values[day.day - 1] = _round10(kg)
        daily[category] = values
    return Forecast(start=start, daily=daily)
