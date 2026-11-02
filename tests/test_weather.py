"""天気（実績・予報）の区分判定と、取得結果の整形。通信はしない（AG-0014）"""
import os
import sys
from datetime import date
from typing import Any, Dict, List

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from weather import (
    Observation, classify_observed, classify_forecast_code, parse_daily_table, parse_forecast,
    build_weather_row,
)

# 2026-11-02 に全国の予報から集めた（天気コード, 区分, 気象庁が配信した文章）。
# 区分は文章から決めた（「所により」「では」「地域」以降の一部地域だけの補足は除く。雪・みぞれ・雨か雪を含めば雪、雨を含めば雨）
JMA_CODE_TEXTS = [
    ("100", "晴", "晴れ"),
    ("101", "晴", "晴れ 時々 くもり"),
    ("111", "晴", "晴れ 夜 くもり"),
    ("112", "雨", "晴れ 後 一時 雨"),
    ("200", "曇", "くもり"),
    ("201", "曇", "くもり 時々 晴れ"),
    ("202", "雨", "くもり 一時 雨"),
    ("203", "雨", "くもり 時々 雨"),
    ("206", "雪", "くもり 一時 雨か雪"),
    ("207", "雪", "くもり 朝晩 雨か雪 所により 夜遅く 雷 を伴う"),
    ("210", "曇", "くもり 昼前 から 時々 晴れ"),
    ("211", "曇", "くもり 夜 晴れ"),
    ("212", "雨", "くもり 後 一時 雨"),
    ("214", "雨", "くもり 夜 雨"),
    ("260", "雪", "くもり 一時 雪か雨"),
    ("300", "雨", "雨 所により 雷 を伴う"),
    ("302", "雨", "雨 夜のはじめ頃 くもり"),
    ("311", "雨", "雨 夜 くもり 後 晴れ"),
    ("313", "雨", "雨 夜 くもり"),
]


@pytest.mark.parametrize("code,expected,text", JMA_CODE_TEXTS)
def test_forecast_code_matches_jma_text(code: str, expected: str, text: str) -> None:
    assert classify_forecast_code(code) == expected, text


def test_forecast_code_unknown_is_blank() -> None:
    for code in ["", "abc", "500", "99", "1000"]:
        assert classify_forecast_code(code) == ""


def test_forecast_code_by_hundreds_digit() -> None:
    """集めた文章に無いコードも、百の位が4（雪）なら雪、3（雨）なら雨"""
    assert classify_forecast_code("400") == "雪"
    assert classify_forecast_code("301") == "雨"


def test_classify_observed_boundaries() -> None:
    """雨=降水量1mm以上、雪=雨かつ日平均2℃以下（推定）、晴=日照6時間以上、曇=それ以外"""
    assert classify_observed(Observation(1.0, 10.0, 0.0)) == "雨"
    assert classify_observed(Observation(0.9, 10.0, 5.9)) == "曇"
    assert classify_observed(Observation(0.9, 10.0, 6.0)) == "晴"
    assert classify_observed(Observation(5.0, 2.0, 0.0)) == "雪"
    assert classify_observed(Observation(5.0, 2.1, 0.0)) == "雨"
    assert classify_observed(Observation(5.0, -0.8, 0.0)) == "雪"   # 2026/02/08（横浜で降雪6cm）の海老名
    assert classify_observed(Observation(0.0, -3.0, 8.0)) == "晴"   # 降水が無ければ寒くても雪にしない


def test_classify_observed_blank_when_missing() -> None:
    assert classify_observed(Observation(None, 10.0, 8.0)) == ""
    assert classify_observed(Observation(3.0, None, 0.0)) == ""
    assert classify_observed(Observation(0.0, 10.0, None)) == ""
    assert classify_observed(Observation(0.0, None, 8.0)) == "晴"   # 雨でなければ気温は要らない


def _row(day: str, values: List[str]) -> str:
    cells = "".join(f"<td><div>{v}</div></td>" for v in [day] + values)
    return f'<tr class="mtx">{cells}</tr>'


def _values(precip: str = "0.0", temp: str = "15.0", sun: str = "7.0") -> List[str]:
    """日別値（アメダス）の1行: 降水量(合計,最大1時間,最大10分) 気温(平均,最高,最低) 湿度(平均,最小)
    風速(平均,最大,風向,最大瞬間,風向) 最多風向 日照 降雪 最深積雪"""
    return [precip, "0.0", "0.0", temp, "20.0", "10.0", "70", "40", "1.0", "3.0", "北", "5.0", "北", "北", sun, "///", "///"]


def test_parse_daily_table_values_and_marks() -> None:
    html = '<table><tr class="mtx"><th>日</th></tr>' + "".join([
        _row("1", _values("0.5", "15.4", "0.4")),
        _row("2", _values("--", "11.0", "--")),            # 「--」は現象なし（降水0・日照0）
        _row("3", _values("3.5)", "9.0)", "1.0")),         # 「)」付きは準正常値として採用
        _row("4", _values("12.0]", "8.0", "2.0")),         # 「]」付きは資料不足で欠損
        _row("5", _values("0.0", "///", "///")),            # 「///」は欠測
    ]) + "</table>"
    table = parse_daily_table(html)
    assert table[1] == Observation(0.5, 15.4, 0.4)
    assert table[2] == Observation(0.0, 11.0, 0.0)
    assert table[3] == Observation(3.5, 9.0, 1.0)
    assert table[4] == Observation(None, 8.0, 2.0)
    assert table[5] == Observation(0.0, None, None)


def test_parse_daily_table_rejects_changed_format() -> None:
    """列数が変わったら、別の列を読み違えないよう使わない"""
    with pytest.raises(ValueError):
        parse_daily_table("<table>" + _row("1", ["0.0", "1.0"]) + "</table>")
    with pytest.raises(ValueError):
        parse_daily_table("<html>メンテナンス中</html>")


def _area(code: str, codes: List[str]) -> Dict[str, Any]:
    return {"area": {"code": code}, "weatherCodes": codes}


def test_parse_forecast_prefers_west_detail_over_prefecture_week() -> None:
    data = [
        {"timeSeries": [{
            "timeDefines": ["2026-11-02T05:00:00+09:00", "2026-11-03T00:00:00+09:00", "2026-11-04T00:00:00+09:00"],
            "areas": [_area("140010", ["300", "300", "300"]),            # 東部（厚木市ではない）
                      _area("140020", ["100", "200", "400"])],           # 西部（厚木市）
        }]},
        {"timeSeries": [{
            "timeDefines": [f"2026-11-0{d}T00:00:00+09:00" for d in range(2, 9)],
            "areas": [_area("140000", ["", "999", "101", "202", "300", "", "100"])],  # 県全体の週間予報
        }]},
    ]
    forecast = parse_forecast(data)
    assert forecast[date(2026, 11, 2)] == "晴"      # 西部の詳細予報が優先される（週間の同日は空欄）
    assert forecast[date(2026, 11, 3)] == "曇"      # 週間の不明コード999は使われない
    assert forecast[date(2026, 11, 4)] == "雪"
    assert forecast[date(2026, 11, 5)] == "雨"      # 4日目以降は県全体の週間予報
    assert forecast[date(2026, 11, 6)] == "雨"
    assert date(2026, 11, 7) not in forecast        # コードが空欄の日は入れない
    assert forecast[date(2026, 11, 8)] == "晴"


def test_build_weather_row_switches_from_observed_to_forecast_at_today() -> None:
    def obs(year: int, month: int) -> Dict[int, Observation]:
        table = {d: Observation(0.0, 10.0, 8.0) for d in range(1, 10)}
        table[5] = Observation(3.0, 10.0, 0.0)
        table[6] = Observation(3.0, 1.0, 0.0)
        return table

    def fc() -> Dict[date, str]:
        return {date(2026, 11, d): "曇" for d in range(10, 17)}

    row = build_weather_row(2026, 11, date(2026, 11, 10), obs, fc)
    assert len(row) == 31
    assert row[:9] == ["晴", "晴", "晴", "晴", "雨", "雪", "晴", "晴", "晴"]   # 1〜9日は実績
    assert row[9:16] == ["曇"] * 7                                       # 10日（今日）以降は予報
    assert row[16:] == [""] * 15                                         # 7日先より後は空欄（30日の月の31日目も空欄）


def test_build_weather_row_finished_month_uses_observed_only() -> None:
    def forecast_must_not_be_called() -> Dict[date, str]:
        raise AssertionError("終わった月は予報を取りに行かない")

    row = build_weather_row(2026, 10, date(2026, 11, 2), lambda y, m: {d: Observation(0.0, 10.0, 8.0) for d in range(1, 32)},
                            forecast_must_not_be_called)
    assert row == ["晴"] * 31


def test_build_weather_row_future_month_uses_forecast_only() -> None:
    def observed_must_not_be_called(year: int, month: int) -> Dict[int, Observation]:
        raise AssertionError("まだ始まっていない月は実績を取りに行かない")

    row = build_weather_row(2026, 12, date(2026, 11, 28), observed_must_not_be_called, lambda: {date(2026, 12, 1): "雨"})
    assert row[0] == "雨" and row[1:] == [""] * 30


def test_build_weather_row_failure_leaves_blank_without_raising() -> None:
    """取得に失敗しても集計は止めない。失敗した側の日だけ空欄にする"""
    def broken_obs(year: int, month: int) -> Dict[int, Observation]:
        raise OSError("気象庁に接続できません")

    def broken_fc() -> Dict[date, str]:
        raise ValueError("形式が変わりました")

    row = build_weather_row(2026, 11, date(2026, 11, 3), broken_obs, lambda: {date(2026, 11, 3): "雨"})
    assert row[:2] == ["", ""] and row[2] == "雨"
    row = build_weather_row(2026, 11, date(2026, 11, 3), lambda y, m: {1: Observation(0.0, 10.0, 8.0)}, broken_fc)
    assert row[0] == "晴" and row[1] == "" and row[2:] == [""] * 29
