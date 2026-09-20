import os
import logging
import pandas as pd
from dotenv import load_dotenv

from google_api import fetch_csv_from_drive, write_to_sheets
from supabase_client import load_to_db, extract_from_db
from aggregate_report import transform_raw_data, build_macro_report, build_micro_report, generate_warnings
from excel_presenter import ExcelReportPresenter

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main() -> None:
    logger.info("ETL パイプラインを開始します。")

    folder_id = os.environ.get("FOLDER_ID")
    if folder_id:
        os.environ["TARGET_FOLDER_ID"] = folder_id

    # [E] Extract
    logger.info("DriveからCSVを取得します...")
    dataframes = fetch_csv_from_drive()
    if not dataframes:
        raise ValueError("Google Driveから対象のCSVデータが1件も取得できませんでした。")

    # [L] Load to DB (raw_nyuka_data)
    logger.info("Supabaseへ生データを保存します...")
    combined_raw = pd.concat(dataframes, ignore_index=True)
    import datetime
    from supabase_client import mark_as_completed
    run_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    source_loading = f"{run_id}_loading"
    source_completed = f"{run_id}_completed"
    
    combined_raw["source_file"] = source_loading
    load_to_db(combined_raw, source_file=source_loading)
    mark_as_completed(source_loading, source_completed)

    # [T] Transform (Split-Pipeline Pattern: Inbound / Outbound Physical Separation)
    logger.info("Supabaseからデータを抽出し、変換処理を行います...")
    raw_df = extract_from_db()
        
    df_inbound, df_outbound = transform_raw_data(raw_df)
    
    # 対象年月の決定（環境変数優先、未指定ならデータの最新月）
    target_yyyymm = os.environ.get("TARGET_YYYYMM")
    if target_yyyymm and "-" in target_yyyymm:
        target_year, target_month = map(int, target_yyyymm.split("-"))
    else:
        temp_date = pd.to_datetime(df_inbound.get("transaction_date", pd.Series()), errors="coerce").dropna()
        if not temp_date.empty:
            latest = temp_date.max()
            target_year, target_month = latest.year, latest.month
        else:
            target_year, target_month = 2026, 8
            
    reiwa_year = target_year - 2018
    sheet_name_micro = f"{reiwa_year}-{target_month}"
    sheet_name_macro = f"{sheet_name_micro}計"
    
    logger.info(f"対象年月: {target_year}年{target_month}月 (令和{reiwa_year}年)")
    
    macro_grid = build_macro_report(df_inbound, df_outbound, target_year=target_year, target_month=target_month)
    micro_grid = build_micro_report(df_inbound, df_outbound, target_year=target_year, target_month=target_month)

    warning_text = generate_warnings(df_inbound)
    if warning_text:
        logger.info(warning_text)

    macro_df = pd.DataFrame(macro_grid)
    micro_df = pd.DataFrame(micro_grid)

    # [L] Load to Sheets
    logger.info("整形済みデータをスプレッドシートへ出力します...")
    # 8-5計は A列(1) から出力（属性テキストを含むため）
    write_to_sheets(macro_df, sheet_name=sheet_name_macro, start_col=1)
    # 8-5 は A列(1) から出力（属性テキストを含むため）
    write_to_sheets(micro_df, sheet_name=sheet_name_micro, start_col=1, warning_text=warning_text)

    # [L] Directive 4: Generate Audit-Grade Excel Ledger using ExcelReportPresenter
    template_path = os.environ.get(
        "EXCEL_TEMPLATE_PATH",
        os.path.join(os.path.dirname(__file__), "..", "Artifacts", "厚木事業所_入荷日報_search.xlsx")
    )
    output_excel_dir = os.environ.get(
        "EXCEL_OUTPUT_DIR",
        os.path.join(os.path.dirname(__file__), "..", "output")
    )
    output_excel_path = os.path.join(
        output_excel_dir,
        f"厚木事業所_入荷日報_{target_year}_{target_month:02d}.xlsx"
    )
    
    if os.path.exists(template_path):
        logger.info(f"監査証跡・雛形数式保持型 Excel 日報を出力します: {output_excel_path}")
        try:
            presenter = ExcelReportPresenter(template_path)
            presenter.render_monthly_report(
                df_inbound=df_inbound,
                df_outbound=df_outbound,
                target_year=target_year,
                target_month=target_month,
                output_path=output_excel_path
            )
            logger.info(f"監査日報 Excel の生成が完了しました: {output_excel_path}")
        except Exception as e:
            logger.error(f"ExcelReportPresenter の実行中にエラーが発生しました: {e}", exc_info=True)
    else:
        logger.warning(f"テンプレートファイルが存在しないため Excel 出力をスキップします: {template_path}")

    logger.info("ETL パイプラインが完了しました。")

if __name__ == "__main__":
    main()
