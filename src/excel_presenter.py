# -*- coding: utf-8 -*-
"""
src/excel_presenter.py

Audit-Grade Template Presenter using openpyxl.
Loads the fixed 887-row master template (Chart of Accounts) from 8-8J,
maps individual tickets to template rows, injects multi-slip arithmetic formulas
(e.g., '=1330+1730+...'), preserves all horizontal and vertical SUM formulas,
retains zero-activity rows for operational monitoring, and clears stale data.
"""

import os
import datetime
from typing import Dict, List, Tuple, Optional, Any, Union
import openpyxl # type: ignore
from openpyxl.worksheet.worksheet import Worksheet # type: ignore
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class ExcelReportPresenter:
    def __init__(self, template_path: str):
        self.template_path = template_path
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"Template Excel file not found: {template_path}")

    def _category_matches(self, cat: str, c_cat: str) -> bool:
        """
        大品目分類（例: '①段ボール', '②新聞'）とテンプレートの見出し（例: '段ボール-持込み', '新聞-バラ持込み'）
        の一致を厳格に判定し、異品目間の誤名寄せ（クロスコンタミネーション）を防止する。
        """
        cat_clean = cat.replace("①", "").replace("②", "").replace("③", "").replace("④", "").replace("⑤", "").strip()
        
        if "段ボール" in cat_clean:
            return "段ボール" in c_cat
        if "新聞" in cat_clean:
            return "新聞" in c_cat
        if "雑誌" in cat_clean:
            return "雑誌" in c_cat
        if "プラ" in cat_clean:
            return "プラ" in c_cat
        if "横持" in cat_clean or "事業所" in cat_clean:
            return "横持" in c_cat or "事業所" in c_cat
        if "その他" in cat_clean:
            return ("その他" in c_cat or "他" in c_cat) and not any(
                k in c_cat for k in ["段ボール", "新聞", "雑誌", "プラ", "横持", "事業所"]
            )
        return False

    def render_monthly_report(
        self,
        df_inbound: pd.DataFrame,
        df_outbound: pd.DataFrame,
        target_year: int,
        target_month: int,
        output_path: str,
        template_sheet_name: str = "8-8J",
        target_sheet_name: Optional[str] = None
    ) -> None:
        """
        テンプレートシートを読み込み、日別セルを初期化（前月データ消去）した上で、
        伝票データを複数件加算数式として注入し、台帳ファイルを生成する。
        """
        wb = openpyxl.load_workbook(self.template_path, data_only=False)
        if template_sheet_name not in wb.sheetnames:
            raise ValueError(f"Template sheet '{template_sheet_name}' not found in workbook.")

        ws: Worksheet = wb[template_sheet_name]
        if target_sheet_name and target_sheet_name != template_sheet_name:
            ws.title = target_sheet_name

        # 1. 1行目・2行目の月度・日付ヘッダー更新
        # 日付列: F列 (col 6 = 1日) 〜 AJ列 (col 36 = 31日)
        for day in range(1, 32):
            col_idx = 5 + day
            try:
                dt = datetime.date(target_year, target_month, day)
                ws.cell(row=2, column=col_idx, value=dt)
            except ValueError:
                ws.cell(row=2, column=col_idx, value=None)

        # 2. テンプレート行のマッピングインデックス構築
        row_index = self._index_template_rows(ws)

        # 3. Directive 3: 日別実績セル（F4:AJ{max_row}）の既存データをクリア（前月残存バグの防止）
        for r in range(4, ws.max_row + 1):
            c2_val = str(ws.cell(row=r, column=2).value or "").strip()
            c1_val = str(ws.cell(row=r, column=1).value or "").strip()
            
            # 合計行および出荷見出し行はスキップ（SUM数式を保護）
            if "合計" in c2_val or "出荷" in c1_val or "＜出荷＞" in c2_val:
                continue
                
            cell_f = ws.cell(row=r, column=6)
            if cell_f.value and str(cell_f.value).startswith("=SUM"):
                continue
                
            for c in range(6, 37):  # Col F(6) to AJ(36)
                ws.cell(row=r, column=c).value = None

        # 4. 対象年月のトランザクション抽出
        df_in_month = self._filter_month(df_inbound, target_year, target_month)
        df_out_month = self._filter_month(df_outbound, target_year, target_month)

        # 5. セル単位（行番号, 日付）での伝票集約
        # Map: (row_number, day) -> List[float]
        cell_slips: Dict[Tuple[int, int], List[float]] = {}

        # 入荷マッピング
        for _, row in df_in_month.iterrows():
            target_row = self._find_inbound_row(row, row_index)
            if target_row:
                day = int(row["_day"])
                weight = float(row["実重量"])
                cell_slips.setdefault((target_row, day), []).append(weight)
            else:
                logger.warning(f"Unmapped inbound slip: {row.get('仕入先名')} ({row.get('大品目分類')}, {row.get('経路分類')})")

        # 出荷マッピング
        for _, row in df_out_month.iterrows():
            target_row = self._find_outbound_row(row, row_index)
            if target_row:
                day = int(row["_day"])
                weight = float(row["実重量"])
                cell_slips.setdefault((target_row, day), []).append(weight)
            else:
                logger.warning(f"Unmapped outbound slip: {row.get('client_name', row.get('得意先名'))} ({row.get('spec_name', row.get('品名'))})")

        # 6. セル値および監査証跡数式の注入
        for (r_idx, day), slips in cell_slips.items():
            col_idx = 5 + day
            cell = ws.cell(row=r_idx, column=col_idx)
            
            if len(slips) == 1:
                # 単一計量伝票: 整数または実数値
                val = slips[0]
                cell.value = int(val) if val.is_integer() else val
            elif len(slips) > 1:
                # 複数計量伝票: 監査証跡加算式（例: '=1330+1730+1280'）
                formula_str = "=" + "+".join(
                    str(int(w)) if w.is_integer() else str(w) for w in slips
                )
                cell.value = formula_str

        # 7. 横計列（AK列, col 37）の数式保護と注入
        for r_idx in range(4, ws.max_row + 1):
            ak_cell = ws.cell(row=r_idx, column=37)
            b_val = ws.cell(row=r_idx, column=2).value
            if b_val and "合計" not in str(b_val):
                if not ak_cell.value or not str(ak_cell.value).startswith("="):
                    ak_cell.value = f"=SUM(F{r_idx}:AJ{r_idx})"

        # 8. 保存
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        wb.save(output_path)
        logger.info(f"Audit-grade report successfully saved to {output_path}")

    def _index_template_rows(self, ws: Worksheet) -> Dict[str, Any]:
        """
        ワークシートを走査し、大品目・経路・取引先に対応する行インデックスを構築する。
        Directive 2に基づき、全カテゴリ・全ルートの『そのた』行を確実に捕捉する。
        """
        index: Dict[str, Any] = {
            "inbound": {},         # (c_cat, c_route, c_supp) -> row_idx
            "inbound_parent": {},  # (c_cat, c_route, c_parent) -> row_idx
            "inbound_sonota": {},  # (c_cat, c_route) -> row_idx
            "outbound": {},        # (c_cat, c_route, c_client, c_item) -> row_idx
        }
        
        current_cat = ""
        current_route = ""
        is_shipping = False

        for r in range(3, ws.max_row + 1):
            c1 = str(ws.cell(r, 1).value or "").strip()
            c2 = str(ws.cell(r, 2).value or "").strip()
            c3 = str(ws.cell(r, 3).value or "").strip()
            c5 = str(ws.cell(r, 5).value or "").strip()

            if "＜出荷＞" in c1:
                is_shipping = True
                continue

            if not is_shipping:
                # A列のセクション見出しの検出（会社名による誤上書きを防止）
                is_header = False
                if c1 and any(k in c1 for k in ["段ボール", "新聞", "雑誌", "プラ", "その他", "事業所間横持ち"]):
                    if not c2 or "合計" in c2 or any(k in c1 for k in ["-", "持込", "回収", "プレス", "横持"]):
                        current_cat = c1
                        is_header = True

                if is_header:
                    continue

                # 小計・合計行の直前の空行を「そのた」フォールバックとして捕捉
                if "合計" in c2:
                    route_key = "持込" if "持込" in current_cat else "引取"
                    if (current_cat, route_key) not in index["inbound_sonota"]:
                        if r - 1 >= 4:
                            index["inbound_sonota"][(current_cat, route_key)] = r - 1
                    continue

                # 明示的な「そのた」行の登録
                if c2 == "そのた":
                    route_key = c5 if c5 in ("持込", "引取") else ("持込" if "持込" in current_cat else "引取")
                    index["inbound_sonota"][(current_cat, route_key)] = r
                elif c2:
                    route_key = c5 if c5 in ("持込", "引取") else ("持込" if "持込" in current_cat else "引取")
                    index["inbound"][(current_cat, route_key, c2)] = r
                    if c1 and not any(k in c1 for k in ["段ボール", "新聞", "雑誌", "プラ", "その他", "横持"]):
                        index["inbound_parent"][(current_cat, route_key, c1)] = r
            else:
                # 出荷セクションの走査
                if c2 in ["①段ボール", "②新聞", "③雑誌", "④プラ類", "⑤その他"]:
                    current_cat = c2
                elif c2 in ["1.輸出", "2.国内"]:
                    current_route = c2
                elif c2 and "合計" not in c2:
                    index["outbound"][(current_cat, current_route, c2, c3)] = r
                    index["outbound"][(current_cat, current_route, c2)] = r

        return index

    def _filter_month(self, df: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
        df = df.copy()
        if "transaction_date" in df.columns:
            df["_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")
            df["_year"] = df["_date"].dt.year
            df["_month"] = df["_date"].dt.month
            df["_day"] = df["_date"].dt.day
            return df[(df["_year"] == year) & (df["_month"] == month)].copy()
        return df.iloc[0:0].copy()

    def _find_inbound_row(self, row: pd.Series, index: Dict[str, Any]) -> Optional[int]:
        """
        Directive 2: 大品目・経路の厳格照合および「そのた」行へのフォールバック。
        """
        cat = str(row.get("大品目分類", "")).strip()
        route = "持込" if "持込" in str(row.get("経路分類", "")) else "引取"
        supplier = str(row.get("仕入先名", "")).strip()
        parent = str(row.get("normalized_parent", row.get("支払先名", ""))).strip()

        # 1. 大品目・経路・取引先の完全一致
        for (c_cat, c_route, c_supp), r_idx in index["inbound"].items():
            if self._category_matches(cat, c_cat) and c_route == route:
                if supplier and (supplier in c_supp or c_supp in supplier):
                    return r_idx

        # 1b. 管理会社（親キー）での一致
        for (c_cat, c_route, c_parent), r_idx in index["inbound_parent"].items():
            if self._category_matches(cat, c_cat) and c_route == route:
                if parent and (parent in c_parent or c_parent in parent):
                    return r_idx

        # 2. 同一大品目・同一経路の「そのた」行へのフォールバック（小口脱落の根絶）
        for (c_cat, c_route), r_idx in index["inbound_sonota"].items():
            if self._category_matches(cat, c_cat) and c_route == route:
                return r_idx
                
        return None

    def _find_outbound_row(self, row: pd.Series, index: Dict[str, Any]) -> Optional[int]:
        cat = str(row.get("大品目分類", "")).strip()
        route = str(row.get("経路分類", "")).strip()
        client = str(row.get("client_name", row.get("得意先名", ""))).strip()
        spec = str(row.get("spec_name", row.get("品名", ""))).strip()

        # 1. 完全一致 (cat, route, client, spec)
        if (cat, route, client, spec) in index["outbound"]:
            return index["outbound"][(cat, route, client, spec)]

        # 2. 取引先名での前方/部分一致（タプル長を安全にハンドリング）
        for key, r_idx in index["outbound"].items():
            if len(key) == 3:
                c_cat, c_route, c_cl = key
                if c_cat == cat and c_route == route and (client in c_cl or c_cl in client):
                    return r_idx
            elif len(key) == 4:
                c_cat, c_route, c_cl, c_spec = key
                if c_cat == cat and c_route == route and (client in c_cl or c_cl in client):
                    if not spec or (spec in c_spec or c_spec in spec):
                        return r_idx
        return None
