# DECISIONS — 設計上の A/B 選択記録

「足す変更」（依存の追加 / src への新規ファイル）は、人間が A/B を選んでから実行する。
本ファイルは alternative_gate.py / closure_check.py が機械的に読む。書式を崩さないこと。

書式:
  ## <ID> <日付> <機能名>
  - choice: A            # A=要求どおり / B=引き算の代替案
  - scope: <対象パス・依存定義ファイルをカンマ区切り。末尾 / でディレクトリ、* でglob可>
  - alternative: <何も足さない案 / 既存の流用・統合案。無ければ「無し」と理由>
  - reason: <その選択の理由>
  - approved-by: human

規則:
  - 1機能につき1エントリ。関係するファイルはまとめて scope に書く（承認疲れを避けるため）
  - ID は AG-0001 から連番
  - 決定は削除しない（履歴として残す）

---

## AG-0001 2026-09-20 openpyxlの追加
- choice: A
- scope: requirements.txt
- alternative: 無し（CIでエラーが発生しているための緊急バグ修正）
- reason: ユーザーからのエラー報告（ModuleNotFoundError: No module named 'openpyxl'）に対する依存関係の補完
- approved-by: human
## AG-0002 2026-09-20 外部マッピングCSVと推測ツールの導入
- choice: A
- scope: src/aggregate_report.py, src/user_mapping_loader.py, .agent/scripts/extract_missing_mappings.py
- alternative: 手動でハードコードを書き換える
- reason: 人間の取捨選択をExcelのコピペだけで完結させ、ソースコードの破損リスクを排除するため
- approved-by: human
## AG-0003 2026-10-04 raw_nyuka_data へのDB往復を廃止しメモリ上で変換
- choice: B
- scope: src/main.py, src/supabase_client.py, src/aggregate_report.py, tests/test_prepare_raw_data.py
- alternative: A=DBへの書き込みは残し、処理成功後に古いスナップショットを削除する
- reason: DBは同じ実行の中で書いてすぐ読み戻す一時置き場で、履歴は参照されていない。毎回のスナップショットが累積してFree枠を187%超過させていたため、中継そのものを廃止する（単純さ・単一の真実源を優先）。挙動を変えないよう、DBが暗黙に行っていた列ホワイトリストと型変換は prepare_raw_data に移す
- approved-by: human
## AG-0004 2026-10-06 出荷の輸出を品目別「輸出合計」に集約（輸出先別の行を廃止）
- choice: B
- scope: src/aggregate_report.py
- alternative: A=事務員の計シートどおり輸出先別（JOP/日商岩井/VIPA等）に行を分ける。輸出先は生データに存在せず自動化不可
- reason: 人間の判断（会話上の選択肢A）。得意先コード8100000(貿易部)⇔輸出 が照合済み出荷伝票で例外0件と確認でき、輸出/国内は生データだけで決定論的に決まる。輸出先は報告上重要でないため、外部情報への依存を持ち込まない
- approved-by: human
## AG-0005 2026-10-06 商品コード9999（臨時品目）の除外と、除外伝票の月次確認一覧
- choice: B
- scope: src/aggregate_report.py, src/main.py, tests/test_bug_reproduction.py, tests/test_aggregate_report.py
- alternative: A=人間が指定した15件どおりに品名キーワード（燃え・燃殻・産廃・銅線）で除外する。列追加は不要だが表記ゆれに弱く、通常取引の銅線も落とす
- reason: 人間の判断（会話上の案A）。除外指定8件はすべて商品コード9999で、事務員も9999の伝票を入出荷とも一度も計上していない。商品マスタで決まるため品名の表記に依存しない（相違はセロハン650kg 1件のみ）。除外は黙って捨てず「R-M除外」シートに理由付きで毎月出し、計上すべきものは人が判断する（必要ならSupabaseのWHITEリストで救済可）。商品コード列を RAW_COLUMNS に追加
- approved-by: human
## AG-0006 2026-10-06 日次・計シートの行は生データから動的に作る（事務員の行マスタは持たない）
- choice: B
- scope: src/aggregate_report.py
- alternative: A=事務員の8-8シートの行一覧（約620行）と「取引先×商品×取引区分×運送店 → 行」の対応をCSVで持ち、事務員と同じ並び・略称・値0の行で出力する
- reason: 集計表の目的は厚木事業所のKPI管理・所長会議資料・経営分析であり、事務員の表との行単位の一致は目的ではない（事務員の表との比較は開発中の正確性検証のため）。行マスタは毎月の行割当と品目区分の二重管理を生むため持たない。正確性は品目×経路の合計で担保する
- approved-by: human
