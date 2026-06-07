"""Convert kanji numeral phrases in bubbles.json files to Arabic numerals.

Touches only patterns whose meaning is clearly numerical (counts, ages,
durations, money amounts). Idiomatic compounds like 一目, 一気, 一切, etc.
are not in the substitution table and pass through unchanged.

Usage:
    uv run python -m src.arabize_bubbles <project_id> [<chapter_id>...]
    uv run python -m src.arabize_bubbles elonmusk main ch2 ch3 ch4 ch5 ch6 ch7 ch8 ch9 ch10
    uv run python -m src.arabize_bubbles --dry-run elonmusk main
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from .project import load


# Phrases listed longest-first so multi-character compounds win over their
# substrings. The script processes them in order.
SUBS: list[tuple[str, str]] = [
    # ===== Money =====
    ("一億八千万ドル", "1億8000万ドル"),
    ("三億七百万ドル", "3億700万ドル"),
    ("六百五十万ドル", "650万ドル"),
    ("二千二百万ドル", "2200万ドル"),
    ("四百四十億ドル", "440億ドル"),
    ("十五億ドル", "15億ドル"),
    ("十六億ドル", "16億ドル"),
    ("二千万ドル", "2000万ドル"),
    ("八千万ドル", "8000万ドル"),
    ("一億ドル", "1億ドル"),
    ("四百二十ドル", "420ドル"),
    ("五百ドル", "500ドル"),

    # ===== Ages =====
    ("二十二歳", "22歳"),
    ("二十三歳", "23歳"),
    ("二十四歳", "24歳"),
    ("二十五歳", "25歳"),
    ("二十六歳", "26歳"),
    ("二十七歳", "27歳"),
    ("二十八歳", "28歳"),
    ("二十九歳", "29歳"),
    ("三十一歳", "31歳"),
    ("三十二歳", "32歳"),
    ("三十三歳", "33歳"),
    ("三十四歳", "34歳"),
    ("三十五歳", "35歳"),
    ("三十六歳", "36歳"),
    ("三十七歳", "37歳"),
    ("三十八歳", "38歳"),
    ("三十九歳", "39歳"),
    ("四十一歳", "41歳"),
    ("四十二歳", "42歳"),
    ("四十三歳", "43歳"),
    ("四十四歳", "44歳"),
    ("四十五歳", "45歳"),
    ("四十六歳", "46歳"),
    ("四十七歳", "47歳"),
    ("四十八歳", "48歳"),
    ("四十九歳", "49歳"),
    ("五十一歳", "51歳"),
    ("五十二歳", "52歳"),
    ("五十三歳", "53歳"),
    ("十一歳", "11歳"),
    ("十二歳", "12歳"),
    ("十三歳", "13歳"),
    ("十四歳", "14歳"),
    ("十五歳", "15歳"),
    ("十六歳", "16歳"),
    ("十七歳", "17歳"),
    ("十八歳", "18歳"),
    ("十九歳", "19歳"),
    ("二十歳", "20歳"),
    ("三十歳", "30歳"),
    ("四十歳", "40歳"),
    ("五十歳", "50歳"),
    ("五歳", "5歳"),
    ("六歳", "6歳"),
    ("七歳", "7歳"),
    ("八歳", "8歳"),
    ("九歳", "9歳"),

    # ===== Years =====
    ("三十七年", "37年"),
    ("四十年", "40年"),
    ("十七年", "17年"),
    ("二年", "2年"),
    ("三年", "3年"),
    ("四年", "4年"),
    ("五年", "5年"),
    ("六年", "6年"),
    ("九年", "9年"),
    ("一年", "1年"),

    # ===== Durations =====
    ("十九時間", "19時間"),
    ("二十五秒", "25秒"),
    ("十週", "10週"),
    ("四週", "4週"),
    ("一週", "1週"),
    ("六ヶ月", "6ヶ月"),
    ("三日", "3日"),
    ("二日", "2日"),
    ("一日", "1日"),
    # NOTE: do not convert bare 「十分」 — ambiguous with 「じゅうぶん」 ("enough").

    # ===== Months (used as date components) =====
    ("一月", "1月"),
    ("二月", "2月"),
    ("三月", "3月"),
    ("四月", "4月"),
    ("五月", "5月"),
    ("六月", "6月"),
    ("七月", "7月"),
    ("八月", "8月"),
    ("九月", "9月"),
    ("十月", "10月"),
    ("十一月", "11月"),
    ("十二月", "12月"),

    # ===== Counts =====
    ("二十七基", "27基"),
    ("九基", "9基"),
    ("十台", "10台"),
    ("一台", "1台"),
    ("二人", "2人"),
    ("一人", "1人"),
    ("三人", "3人"),
    ("四人", "4人"),
    ("五人", "5人"),
    ("二本", "2本"),
    ("一本", "1本"),
    ("二冊", "2冊"),
    ("一冊", "1冊"),
    ("三つ", "3つ"),
    ("二つ", "2つ"),
    ("一つ", "1つ"),
    ("一段", "1段"),
    ("二段", "2段"),
    ("三段", "3段"),
    ("三度目", "3度目"),
    ("二度目", "2度目"),
    ("一度", "1度"),
    ("二度", "2度"),
    ("三度", "3度"),
    ("二回", "2回"),
    ("一回", "1回"),
    ("三回", "3回"),

    # ===== Distances / measurements =====
    ("五百メートル", "500メートル"),
    ("二百メートル", "200メートル"),
    ("八十メートル", "80メートル"),
    ("十メートル", "10メートル"),
    ("四百キロメートル", "400キロメートル"),
    ("五十度", "50度"),
    ("摂氏五十度", "摂氏50度"),

    # ===== Percent / multipliers =====
    ("五千パーセント", "5000パーセント"),
    ("十五パーセント", "15パーセント"),
    ("二十パーセント", "20パーセント"),
    ("二パーセント", "2パーセント"),
    ("五倍", "5倍"),
    ("三倍", "3倍"),

    # ===== Big-number people counts =====
    ("二十万人", "20万人"),
    ("四十万人", "40万人"),
    ("二十二人", "22人"),
    # NOTE: do not convert bare 「千人」 — it breaks idiomatic 何千人 ("thousands of").

    # ===== 「九点二」 etc =====
    ("九点二", "9.2"),
]


def arabize(text: str) -> str:
    out = text
    for src, dst in SUBS:
        out = out.replace(src, dst)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("project_id")
    parser.add_argument("chapter_ids", nargs="*", help="Defaults to all chapters with bubbles.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    project = load(args.project_id)
    if args.chapter_ids:
        chapters = [project.chapter(cid) for cid in args.chapter_ids]
    else:
        chapters = [c for c in project.chapters if c.bubbles_json.exists()]

    total_changes = 0
    for ch in chapters:
        if not ch.bubbles_json.exists():
            print(f"skip {ch.id}: no bubbles.json")
            continue
        text = ch.bubbles_json.read_text(encoding="utf-8")
        new_text = arabize(text)
        changes = sum(text.count(s) for s, _ in SUBS if s in text)
        if new_text == text:
            print(f"  {ch.id}: no changes")
            continue
        print(f"  {ch.id}: {changes} substitution(s)")
        total_changes += changes
        if not args.dry_run:
            ch.bubbles_json.write_text(new_text, encoding="utf-8")
    print(f"\n{'(dry run) ' if args.dry_run else ''}total: {total_changes} substitution(s)")


if __name__ == "__main__":
    main()
