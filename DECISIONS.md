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
