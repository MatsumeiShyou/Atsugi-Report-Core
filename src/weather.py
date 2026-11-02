"""日次シートの「天気」行を作る（AG-0014）。

実績は気象庁「過去の気象データ」の海老名観測所の日別値（厚木には観測所が無い最寄り）、
予報は気象庁の神奈川県の予報から、1日ごとに 晴・曇・雨・雪 のいずれかにする。
外部通信はこのファイルに閉じ込める。取得できなかった日は空欄にし、集計は止めない。
"""
import json
import logging
import re
import calendar
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, NamedTuple, Optional

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))
OBSERVATION_URL = ("https://www.data.jma.go.jp/stats/etrn/view/daily_a1.php"
                   "?prec_no=46&block_no=0388&year={year}&month={month}&day=1&view=")
FORECAST_URL = "https://www.jma.go.jp/bosai/forecast/data/forecast/140000.json"
WEST_AREA_CODE = "140020"        # 神奈川県西部（厚木市の予報区）。3日先までの詳細予報
PREFECTURE_AREA_CODE = "140000"  # 神奈川県全体。4日目以降の週間予報は県全体の値しかない
ATTRIBUTION = ("出典：気象庁ホームページ（過去の気象データ 海老名観測所の日別値、神奈川県の天気予報）。"
               "気象庁のデータを当方で晴・曇・雨・雪に加工して表示。雪は降水量と気温からの推定、予報は最大7日先まで")

RAIN_MM = 1.0           # 降水量がこれ以上の日を「雨」（気象庁の降水日の定義）
SNOW_MAX_AVG_TEMP = 2.0  # 雨の日のうち日平均気温がこれ以下なら「雪」と推定（海老名は降雪を観測しない）
SUNNY_HOURS = 6.0       # 雨でない日のうち日照時間がこれ以上なら「晴」、未満は「曇」
OBSERVATION_COLUMNS = 18  # 日別値の1行のセル数。変わっていたら形式変更とみなして使わない


class Observation(NamedTuple):
    precipitation: Optional[float]  # 降水量の合計(mm)
    avg_temp: Optional[float]       # 日平均気温(℃)
    sunshine: Optional[float]       # 日照時間(h)


def classify_observed(obs: Observation) -> str:
    """観測値を 晴・曇・雨・雪 にする。判定に必要な値が欠けていれば空欄"""
    if obs.precipitation is None:
        return ""
    if obs.precipitation >= RAIN_MM:
        if obs.avg_temp is None:
            return ""
        return "雪" if obs.avg_temp <= SNOW_MAX_AVG_TEMP else "雨"
    if obs.sunshine is None:
        return ""
    return "晴" if obs.sunshine >= SUNNY_HOURS else "曇"


# 気象庁の天気コード。百の位が主な天気（1=晴 2=曇 3=雨 4=雪）で、下2桁が「時々」「のち」「一時」などの組み合わせ。
# 雪・みぞれ・雨か雪を含むコード、雨を含む晴・曇のコードは個別に持つ。
# 全国の予報から集めた19コードの文章で確認済み（tests/test_weather.py）。残りは気象庁の命名規則による
_SNOW_CODES = {104, 105, 106, 107, 115, 116, 117, 118, 124, 160, 170, 181,
               204, 205, 206, 207, 215, 216, 217, 218, 228, 229, 230, 250, 260, 270, 281,
               303, 304, 309, 314, 315, 316, 317, 322, 326, 327, 329, 340, 361, 371}
_RAIN_IN_SUNNY_OR_CLOUDY = {102, 103, 108, 112, 113, 114, 119, 120, 121, 122, 123, 125, 126, 127, 128, 140,
                            202, 203, 208, 212, 213, 214, 219, 220, 221, 222, 224, 225, 226, 240}


def classify_forecast_code(code: str) -> str:
    """気象庁の天気コードを 晴・曇・雨・雪 にする。雪・みぞれ・雨か雪を含めば雪、雨を含めば雨。不明なコードは空欄"""
    if not re.fullmatch(r"[1-4]\d\d", code or ""):
        return ""
    number = int(code)
    if number // 100 == 4 or number in _SNOW_CODES:
        return "雪"
    if number // 100 == 3 or number in _RAIN_IN_SUNNY_OR_CLOUDY:
        return "雨"
    return "晴" if number // 100 == 1 else "曇"


def _number(cell: str, none_means_zero: bool = False) -> Optional[float]:
    """日別値のセルを数値にする。「)」付きは準正常値として採用、「]」付き（資料不足）や「///」（欠測）は欠損"""
    text = cell.strip()
    if text == "--":
        return 0.0 if none_means_zero else None
    match = re.fullmatch(r"(-?\d+(?:\.\d+)?)\)?", text)
    return float(match.group(1)) if match else None


def parse_daily_table(html: str) -> Dict[int, Observation]:
    """気象庁の日別値（アメダス）のHTMLを、日 → 観測値 にする。形式が想定と違えば ValueError"""
    result: Dict[int, Observation] = {}
    for row in re.findall(r'<tr class="mtx"[^>]*>(.*?)</tr>', html, re.S):
        cells = [re.sub(r"<[^>]+>|\s+", "", c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        if not cells or not cells[0].isdigit():
            continue  # 見出し行
        if len(cells) != OBSERVATION_COLUMNS:
            raise ValueError(f"日別値の列数が想定({OBSERVATION_COLUMNS})と異なります: {len(cells)}")
        # 0:日 1:降水量合計 4:平均気温 15:日照時間
        result[int(cells[0])] = Observation(_number(cells[1], True), _number(cells[4]), _number(cells[15], True))
    if not result:
        raise ValueError("日別値の表が見つかりません")
    return result


def parse_forecast(data: List[Any]) -> Dict[date, str]:
    """気象庁の予報JSONを、日付 → 区分 にする。週間予報（県全体）の上に3日先までの詳細予報（西部）を重ねる"""
    layers: Dict[int, Dict[date, str]] = {1: {}, 2: {}}
    for block in data:
        for series in block.get("timeSeries", []):
            for area in series.get("areas", []):
                code = area.get("area", {}).get("code")
                layer = 2 if code == WEST_AREA_CODE else 1 if code == PREFECTURE_AREA_CODE else 0
                if not layer or "weatherCodes" not in area:
                    continue
                for time_text, weather_code in zip(series["timeDefines"], area["weatherCodes"]):
                    day = date.fromisoformat(time_text[:10])
                    category = classify_forecast_code(weather_code)
                    if category and day not in layers[layer]:
                        layers[layer][day] = category
    return {**layers[1], **layers[2]}


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=20) as response:
        data: bytes = response.read()
        return data


def fetch_observation(year: int, month: int) -> Dict[int, Observation]:
    html = _get(OBSERVATION_URL.format(year=year, month=month)).decode("utf-8", "replace")
    return parse_daily_table(html)


def fetch_forecast() -> Dict[date, str]:
    return parse_forecast(json.loads(_get(FORECAST_URL)))


def build_weather_row(
    year: int,
    month: int,
    today: Optional[date] = None,
    fetch_obs: Callable[[int, int], Dict[int, Observation]] = fetch_observation,
    fetch_fc: Callable[[], Dict[date, str]] = fetch_forecast,
) -> List[str]:
    """対象月の1日〜31日の天気（晴・曇・雨・雪）。今日より前は実績、今日以降は予報。取得できない日は空欄"""
    today = today or datetime.now(JST).date()
    days_in_month = calendar.monthrange(year, month)[1]
    dates = [date(year, month, d) for d in range(1, days_in_month + 1)]

    observed: Dict[int, Observation] = {}
    if dates[0] < today:
        try:
            observed = fetch_obs(year, month)
        except Exception as e:
            logger.warning(f"天気の実績を取得できませんでした（空欄にします）: {e}")
    forecast: Dict[date, str] = {}
    if dates[-1] >= today:
        try:
            forecast = fetch_fc()
        except Exception as e:
            logger.warning(f"天気の予報を取得できませんでした（空欄にします）: {e}")

    row = []
    for d in dates:
        if d < today:
            obs = observed.get(d.day)
            row.append(classify_observed(obs) if obs else "")
        else:
            row.append(forecast.get(d, ""))
    return row + [""] * (31 - len(row))
