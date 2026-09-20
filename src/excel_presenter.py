# -*- coding: utf-8 -*-
"""
src/excel_presenter.py

シンプル化・引き算された新しいExcel出力モジュール。
雛形Excelへの複雑な数式注入（Template Injection）を撤廃し、
Pandasのpivot_tableを用いてゼロベースでクロス集計表を生成・出力します。
これにより、行の欠落や数式破壊などのバグを根絶します。
"""

import os
import datetime
import pandas as pd
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class ExcelReportPresenter:
    def __init__(self, template_path: str):
        # 以前の互換性のために引数は受け取るが、雛形は使用しない（ゼロベース描画）
        self.template_path = template_path
        logger.info("ExcelReportPresenter: 雛形注入を撤廃し、ゼロベースのクロス集計モードで動作します。")

    def _filter_month(self, df: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
        df = df.copy()
        if "transaction_date" in df.columns:
            df["_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")
            df["_year"] = df["_date"].dt.year
            df["_month"] = df["_date"].dt.month
            df["_day"] = df["_date"].dt.day
            return df[(df["_year"] == year) & (df["_month"] == month)].copy()
        return df.iloc[0:0].copy()

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
        対象年月のトランザクションを抽出し、Pandasで日別のクロス集計表を作成。
        静的な結果として新しいExcelファイルを出力します。
        """
        # 1. 対象月のデータ抽出
        df_in = self._filter_month(df_inbound, target_year, target_month)
        df_out = self._filter_month(df_outbound, target_year, target_month)
        
        # 2. 入荷データのクロス集計 (大分類 > 経路 > 取引先)
        # 取引先名は「管理会社（親キー）」があればそれ、なければ仕入先名
        if not df_in.empty:
            df_in["取引先名"] = df_in["normalized_parent"].fillna(df_in["仕入先名"])
            # NaNを埋める
            df_in["大品目分類"] = df_in["大品目分類"].fillna("未分類")
            df_in["経路分類"] = df_in["経路分類"].fillna("未分類")
            df_in["取引先名"] = df_in["取引先名"].fillna("未分類")
            
            pivot_in = pd.pivot_table(
                df_in,
                values="実重量",
                index=["大品目分類", "経路分類", "取引先名"],
                columns=["_day"],
                aggfunc="sum",
                fill_value=0
            )
            # 横計（総合計）
            pivot_in["合計"] = pivot_in.sum(axis=1)
        else:
            pivot_in = pd.DataFrame()

        # 3. 出荷データのクロス集計 (大分類 > 経路 > 得意先 > 品名)
        if not df_out.empty:
            df_out["得意先名"] = df_out["client_name"].fillna(df_out["得意先名"])
            df_out["品名"] = df_out["spec_name"].fillna(df_out["品名"])
            df_out["大品目分類"] = df_out["大品目分類"].fillna("未分類")
            df_out["経路分類"] = df_out["経路分類"].fillna("未分類")
            df_out["得意先名"] = df_out["得意先名"].fillna("未分類")
            df_out["品名"] = df_out["品名"].fillna("未分類")

            pivot_out = pd.pivot_table(
                df_out,
                values="実重量",
                index=["大品目分類", "経路分類", "得意先名", "品名"],
                columns=["_day"],
                aggfunc="sum",
                fill_value=0
            )
            pivot_out["合計"] = pivot_out.sum(axis=1)
        else:
            pivot_out = pd.DataFrame()

        # 4. 出力先ディレクトリの確保とExcel書き出し
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            sheet_name = target_sheet_name if target_sheet_name else template_sheet_name
            # 入荷データを書き込み
            if not pivot_in.empty:
                pivot_in.to_excel(writer, sheet_name=sheet_name, startrow=0)
            else:
                pd.DataFrame(["入荷データなし"]).to_excel(writer, sheet_name=sheet_name, startrow=0, index=False)
            
            # 1行空けて出荷データを書き込み
            start_row_out = len(pivot_in) + 4 if not pivot_in.empty else 2
            
            # 出荷見出し行
            ws = writer.sheets[sheet_name]
            ws.cell(row=start_row_out, column=1, value="＜出荷＞")
            
            if not pivot_out.empty:
                pivot_out.to_excel(writer, sheet_name=sheet_name, startrow=start_row_out)
            else:
                pd.DataFrame(["出荷データなし"]).to_excel(writer, sheet_name=sheet_name, startrow=start_row_out, index=False)
                
        logger.info(f"シンプル化された日報（クロス集計版）を {output_path} に保存しました。")
