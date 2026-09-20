#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
closure_check.py — 完了前ゲート（PreToolUse をすり抜けた「足す」変更の最終確認）

やること:
  1. 作業ツリーの差分を見て「足した」ものを数える
       - src/ 配下の新規 .py ファイル
       - 依存定義ファイルの変更
       - 純増行数
  2. 新規ファイル / 依存変更に対応する承認済み DECISIONS.md エントリが無ければ ERROR
  3. DECISIONS.md の書式不備（必須項目欠落）を ERROR
  4. 純増行数が閾値超過なら WARN（止めはしない）

使い方:
  python .agent/scripts/closure_check.py          # 完了前チェック
  python .agent/scripts/closure_check.py --stats  # 発動回数・A/B選択率の集計
  python .agent/scripts/closure_check.py --base HEAD~3   # 比較元を変える

終了コード: 0 = OK / 1 = ERROR あり
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from alternative_gate import (  # noqa: E402
    DECISIONS_FILE, DEP_FILES, LOG_FILE, REQUIRED_FIELDS, SRC_DIRS, SRC_SUFFIXES,
    eprint, find_decision, find_root, is_valid, read_decisions,
)

NET_ADDED_WARN = 300  # 純増行数の警告閾値

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=root, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return r.stdout if r.returncode == 0 else ""


def is_src(rel: str) -> bool:
    return rel.startswith(tuple(d + "/" for d in SRC_DIRS)) and rel.endswith(SRC_SUFFIXES)


def is_dep(rel: str) -> bool:
    return rel.rsplit("/", 1)[-1] in DEP_FILES


def collect_changes(root: Path, base: str):
    """(新規srcファイル, 変更された依存定義, 純増行数) を返す。"""
    new_src, dep_changed, net = [], [], 0

    for line in git(root, "status", "--porcelain=v1", "-uall").splitlines():
        if len(line) < 4:
            continue
        status, rel = line[:2], line[3:].strip().strip('"')
        rel = rel.split(" -> ")[-1].replace("\\", "/")
        if is_dep(rel):
            dep_changed.append(rel)
        if is_src(rel) and ("?" in status or "A" in status):
            new_src.append(rel)
            try:
                net += len((root / rel).read_text(encoding="utf-8",
                                                  errors="replace").splitlines())
            except Exception:
                pass

    for line in git(root, "diff", base, "--numstat").splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        add, dele, rel = parts
        rel = rel.replace("\\", "/")
        if add.isdigit() and dele.isdigit():
            net += int(add) - int(dele)
        if is_dep(rel) and rel not in dep_changed:
            dep_changed.append(rel)

    return sorted(set(new_src)), sorted(set(dep_changed)), net


def show_stats(root: Path) -> int:
    log_path = root / LOG_FILE
    events: Counter = Counter()
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                events[json.loads(line).get("event", "?")] += 1
            except Exception:
                continue

    entries = read_decisions(root)
    choices = Counter((e["fields"].get("choice", "?").strip().upper()) for e in entries)

    print("== ゲート発動状況 ==")
    for k in ("block", "allow", "bypass"):
        print(f"  {k:<7}: {events.get(k, 0)}")
    print("== 決定の内訳 ==")
    print(f"  総数   : {len(entries)}")
    print(f"  A(要求): {choices.get('A', 0)}")
    print(f"  B(代替): {choices.get('B', 0)}")
    total = choices.get("A", 0) + choices.get("B", 0)
    if total == 0:
        print("\n  → 決定が0件。ゲートが飾りになっていないか確認してください。")
    elif choices.get("B", 0) == 0:
        print("\n  → B(引き算)が0件。トリガーが的外れか、代替案が形式化しています。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="完了前ゲート")
    ap.add_argument("--root", default=None)
    ap.add_argument("--base", default="HEAD", help="差分の比較元（既定: HEAD）")
    ap.add_argument("--stats", action="store_true", help="集計のみ表示")
    args = ap.parse_args()

    root = Path(args.root) if args.root else find_root(Path.cwd())
    if args.stats:
        return show_stats(root)

    errors, warns = [], []
    entries = read_decisions(root)

    # 書式不備の検査
    for e in entries:
        if not is_valid(e):
            missing = [k for k in REQUIRED_FIELDS if not e["fields"].get(k)]
            reason = f"必須項目の欠落: {', '.join(missing)}" if missing \
                else "choice が A/B でない、または approved-by が human でない"
            errors.append(f"{DECISIONS_FILE} {e['id']}: {reason}")

    new_src, dep_changed, net = collect_changes(root, args.base)

    for rel in new_src + dep_changed:
        if find_decision(rel, entries) is None:
            kind = "新規ファイル" if rel in new_src else "依存変更"
            errors.append(f"未承認の{kind}: {rel}（DECISIONS.md に scope 一致する決定が無い）")

    if net > NET_ADDED_WARN:
        warns.append(f"純増 {net} 行（閾値 {NET_ADDED_WARN}）。"
                     "引き算できる箇所が無いか、報告で1行触れてください。")

    print(f"新規 src ファイル: {len(new_src)} / 依存定義の変更: {len(dep_changed)} / 純増: {net} 行")
    for w in warns:
        print(f"[WARN] {w}")
    for e in errors:
        eprint(f"[ERROR] {e}")

    if errors:
        eprint("\n完了不可。要求どおりで進めるなら DECISIONS.md に "
               "choice: A のエントリを人間の選択として追記してください。")
        return 1

    print("[OK] 完了前ゲート通過")
    return 0


if __name__ == "__main__":
    sys.exit(main())
