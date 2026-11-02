"""シートの文字色の指示（通信はしない）。予測のセルだけを赤字にし、毎回その前に色を戻す（AG-0015）"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from google_api import build_color_requests, RED


def _range(request: dict) -> tuple:
    r = request["repeatCell"]["range"]
    return (r["startRowIndex"], r["endRowIndex"], r["startColumnIndex"], r["endColumnIndex"])


def test_first_request_resets_color_of_whole_written_range() -> None:
    """値を消しても書式は残るので、前回の赤字が別の位置に残らないよう、最初に範囲全体を既定の色に戻す"""
    requests = build_color_requests(sheet_id=7, n_rows=100, n_cols=39, red_cells=[], row_offset=3)
    assert len(requests) == 1
    reset = requests[0]["repeatCell"]
    assert reset["range"]["sheetId"] == 7
    assert _range(requests[0]) == (0, 103, 0, 39)
    assert reset["cell"] == {} and reset["fields"] == "userEnteredFormat.textFormat.foregroundColor"


def test_red_cells_are_merged_by_adjacent_columns_per_row() -> None:
    cells = [(5, 7), (5, 8), (5, 9), (5, 12), (9, 7)]
    requests = build_color_requests(sheet_id=1, n_rows=20, n_cols=39, red_cells=cells)
    ranges = [_range(r) for r in requests[1:]]
    assert ranges == [(5, 6, 7, 10), (5, 6, 12, 13), (9, 10, 7, 8)]
    for request in requests[1:]:
        assert request["repeatCell"]["cell"]["userEnteredFormat"]["textFormat"]["foregroundColor"] == RED


def test_offsets_shift_rows_and_columns() -> None:
    """表の上に注記の行がある場合や、表が途中の列から始まる場合に、赤字の位置がずれない"""
    requests = build_color_requests(sheet_id=1, n_rows=20, n_cols=39, red_cells=[(2, 3)], row_offset=4, col_offset=1)
    assert _range(requests[1]) == (6, 7, 4, 5)


def test_duplicate_cells_are_ignored() -> None:
    requests = build_color_requests(sheet_id=1, n_rows=5, n_cols=5, red_cells=[(1, 1), (1, 1)])
    assert [_range(r) for r in requests[1:]] == [(1, 2, 1, 2)]
