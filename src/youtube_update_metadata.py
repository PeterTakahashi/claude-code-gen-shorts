"""Rewrite YouTube video description/tags in-place for SEO.

Uses YouTube Data API v3 `videos.update` (cost: 50 quota units per call).

For each active short on a channel, generates an SEO-enriched description that
adds: person canonical name (JP + EN + aliases), related companies/products,
channel link, and an expanded hashtag list. Tags are likewise enriched.

Existing description is preserved as the lead — only the trailing "▼関連" /
hashtag block is replaced (idempotent: re-running finds the marker and rewrites
only the trailing block, not the lead).

Usage:
  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_update_metadata \
      --channel ijinden_ja --kind short --dry-run

  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_update_metadata \
      --channel ijinden_ja --kind short --series stevejobs

  PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_update_metadata \
      --channel ijinden_ja                          # all kinds, all series
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from googleapiclient.errors import HttpError
from googleapiclient.discovery import build

from .db import connect
from .youtube_upload import get_credentials, DEFAULT_CLIENT_SECRET, resolve_channel_token

# Marker delimits the lead text (kept as-is on re-run) from the SEO block (regenerated).
MARKER = "\n\n▼関連キーワード"


# series_id → SEO metadata. Add a series here when a new biography is published.
PEOPLE: dict[str, dict] = {
    "stevejobs": {
        "name_jp": "スティーブ・ジョブズ", "name_en": "Steve Jobs", "aliases_en": ["Steven Paul Jobs"],
        "topics": ["Apple", "iPhone", "Mac", "Pixar", "NeXT", "iPod", "iPad", "Atari"],
    },
    "elonmusk": {
        "name_jp": "イーロン・マスク", "name_en": "Elon Musk", "aliases_en": ["Elon Reeve Musk"],
        "topics": ["Tesla", "SpaceX", "Twitter", "X", "PayPal", "OpenAI", "Neuralink", "xAI", "Falcon"],
    },
    "samaltman": {
        "name_jp": "サム・アルトマン", "name_en": "Sam Altman", "aliases_en": ["Samuel Harris Altman"],
        "topics": ["OpenAI", "ChatGPT", "Y Combinator", "Loopt", "Worldcoin", "GPT-4"],
    },
    "darioamodei": {
        "name_jp": "ダリオ・アモデイ", "name_en": "Dario Amodei", "aliases_en": [],
        "topics": ["Anthropic", "Claude", "OpenAI", "AI Safety", "ChatGPT", "Daniela Amodei"],
    },
    "jensenhuang": {
        "name_jp": "ジェンスン・フアン", "name_en": "Jensen Huang", "aliases_en": ["Jen-Hsun Huang", "黄仁勲"],
        "topics": ["Nvidia", "GPU", "CUDA", "GeForce", "H100", "AI半導体"],
    },
    "masayoshison": {
        "name_jp": "孫正義", "name_en": "Masayoshi Son", "aliases_en": ["Son Masayoshi"],
        "topics": ["SoftBank", "ソフトバンク", "Yahoo", "ARM", "Alibaba", "WeWork", "Vision Fund"],
    },
    "tadashiyanai": {
        "name_jp": "柳井正", "name_en": "Tadashi Yanai", "aliases_en": [],
        "topics": ["UNIQLO", "ユニクロ", "ファーストリテイリング", "Fast Retailing", "GU", "宇部"],
    },
    "markzuckerberg": {
        "name_jp": "マーク・ザッカーバーグ", "name_en": "Mark Zuckerberg", "aliases_en": ["Mark Elliot Zuckerberg"],
        "topics": ["Facebook", "Meta", "Instagram", "WhatsApp", "Oculus", "Metaverse", "Harvard"],
    },
    "takafumihorie": {
        "name_jp": "堀江貴文", "name_en": "Takafumi Horie", "aliases_en": ["ホリエモン"],
        "topics": ["ライブドア", "Livedoor", "インターステラテクノロジズ", "ロケット", "プロ野球", "近鉄"],
    },
    "billgates": {
        "name_jp": "ビル・ゲイツ", "name_en": "Bill Gates", "aliases_en": ["William Henry Gates III"],
        "topics": ["Microsoft", "Windows", "MS-DOS", "Harvard", "ゲイツ財団", "Gates Foundation", "Altair"],
    },
    "jeffbezos": {
        "name_jp": "ジェフ・ベゾス", "name_en": "Jeff Bezos", "aliases_en": ["Jeffrey Preston Bezos"],
        "topics": ["Amazon", "AWS", "Blue Origin", "Kindle", "Washington Post", "Prime"],
    },
    "larrypage": {
        "name_jp": "ラリー・ペイジ", "name_en": "Larry Page", "aliases_en": ["Lawrence Edward Page"],
        "topics": ["Google", "Alphabet", "PageRank", "Stanford", "Sergey Brin", "Android"],
    },
    "paulgraham": {
        "name_jp": "ポール・グレアム", "name_en": "Paul Graham", "aliases_en": [],
        "topics": ["Y Combinator", "YC", "Viaweb", "Yahoo", "Hacker News", "Lisp", "Arc"],
    },
    "vitalikbuterin": {
        "name_jp": "ヴィタリック・ブテリン", "name_en": "Vitalik Buterin", "aliases_en": ["Vitaly Buterin", "Виталик Бутерин"],
        "topics": ["Ethereum", "イーサリアム", "Bitcoin", "SHIB", "The Merge", "Proof of Stake", "ブロックチェーン"],
    },
    "sambankmanfried": {
        "name_jp": "サム・バンクマン=フリード", "name_en": "Sam Bankman-Fried", "aliases_en": ["SBF", "Samuel Benjamin Bankman-Fried"],
        "topics": ["FTX", "Alameda Research", "MIT", "Effective Altruism", "暗号資産", "Crypto"],
    },
    "marcandreessen": {
        "name_jp": "マーク・アンドリーセン", "name_en": "Marc Andreessen", "aliases_en": [],
        "topics": ["Netscape", "Mosaic", "a16z", "Andreessen Horowitz", "Software is Eating the World", "Web"],
    },
    "georgehotz": {
        "name_jp": "ジョージ・ホッツ", "name_en": "George Hotz", "aliases_en": ["geohot"],
        "topics": ["comma.ai", "tinygrad", "iPhone Jailbreak", "PS3", "Sony", "Twitter", "Tesla"],
    },
    "tomokonamba": {
        "name_jp": "南場智子", "name_en": "Tomoko Namba", "aliases_en": [],
        "topics": ["DeNA", "ディー・エヌ・エー", "Mobage", "モバゲー", "横浜DeNAベイスターズ", "マッキンゼー", "McKinsey"],
    },
    "susumufujita": {
        "name_jp": "藤田晋", "name_en": "Susumu Fujita", "aliases_en": [],
        "topics": ["サイバーエージェント", "CyberAgent", "Ameba", "AbemaTV", "ABEMA", "M League"],
    },
    "keishikameyama": {
        "name_jp": "亀山敬司", "name_en": "Keishi Kameyama", "aliases_en": [],
        "topics": ["DMM", "DMM.com", "石川県", "貸ビデオ", "六本木ヒルズ", "テキ屋"],
    },
    "larryellison": {
        "name_jp": "ラリー・エリソン", "name_en": "Larry Ellison", "aliases_en": ["Lawrence Joseph Ellison"],
        "topics": ["Oracle", "Lanai", "ラナイ島", "Hawaii", "ハワイ", "Silicon Valley", "America's Cup", "NetSuite"],
    },
    "theranos": {
        "name_jp": "エリザベス・ホームズ", "name_en": "Elizabeth Holmes", "aliases_en": [],
        "topics": ["Theranos", "Edison", "Silicon Valley", "シリコンバレー", "Stanford", "詐欺", "scandal", "血液検査"],
    },
    "snowbrand_poisoning": {
        "name_jp": "雪印乳業", "name_en": "Snow Brand Milk", "aliases_en": ["Snow Brand Foods"],
        "topics": ["雪印", "Snow Brand", "食中毒", "黄色ブドウ球菌", "脱脂粉乳", "大阪", "Osaka", "scandal"],
    },
    "wework": {
        "name_jp": "アダム・ニューマン", "name_en": "Adam Neumann", "aliases_en": [],
        "topics": ["WeWork", "ウィーワーク", "SoftBank", "ソフトバンク", "孫正義", "Masayoshi Son", "IPO", "scandal"],
    },
}


CHANNEL_LINKS = {
    "ijinden_ja": "https://www.youtube.com/@baltoon-ai",
    "baltoon_biography_en": "https://www.youtube.com/@BaltoonBiography",
    "baltoon_incidents_ja": "https://www.youtube.com/channel/UC5z0hxkyTRFYQm0bn3QLjPQ",
}


def _build_seo_block(series_id: str, channel_id: str | None, kind: str) -> str:
    """Return the SEO trailing block (replaces everything after MARKER)."""
    p = PEOPLE.get(series_id)
    if not p:
        # No mapping → minimal block with just generic hashtags + channel link.
        return f"{MARKER}\n#Shorts #人物伝 #偉人伝 #ビジネス"

    name_jp = p["name_jp"]
    name_en = p["name_en"]
    aliases_en = p.get("aliases_en") or []
    topics = p.get("topics") or []

    name_line = f"{name_jp} / {name_en}"
    if aliases_en:
        name_line += " (" + " / ".join(aliases_en) + ")"

    topics_line = " / ".join(topics) if topics else ""

    lines = [
        MARKER.lstrip("\n"),  # start a fresh paragraph
        f"{name_line}",
    ]
    if topics_line:
        lines.append(f"関連: {topics_line}")

    # Channel link.
    link = CHANNEL_LINKS.get(channel_id or "")
    if link:
        lines.append(f"\nチャンネル: {link}")

    # Hashtag block — must include #Shorts for shorts.
    hashtags = ["#Shorts"] if kind == "short" else []
    hashtags += [
        # Hashtag rules: no spaces, no punctuation in hashtag.
        "#" + _hashtagify(name_jp),
        "#" + _hashtagify(name_en).replace(" ", ""),
    ]
    for a in aliases_en:
        h = "#" + _hashtagify(a).replace(" ", "")
        if h not in hashtags and 2 < len(h) <= 32:
            hashtags.append(h)
    for t in topics[:6]:  # cap to keep total under YouTube's 15-hashtag limit
        h = "#" + _hashtagify(t).replace(" ", "").replace(".", "").replace("=", "")
        if h not in hashtags and 2 < len(h) <= 32:
            hashtags.append(h)
    # Generic tags last
    for g in ("#人物伝", "#偉人伝", "#ビジネス", "#起業家"):
        if g not in hashtags:
            hashtags.append(g)

    lines.append("")
    lines.append(" ".join(hashtags[:15]))  # YouTube hard-limits hashtags

    return "\n" + "\n".join(lines)


def _hashtagify(s: str) -> str:
    """Strip characters that YouTube rejects in hashtags."""
    bad = "・=#@,.:;!?\"'()[]{}<>/\\|`~^&%*+"
    return "".join(c for c in s if c not in bad)


def _build_tags(series_id: str, existing: list[str] | None) -> list[str]:
    """Build the new tags list — preserves existing then adds person + topics."""
    existing = list(existing or [])
    seen = {t.lower() for t in existing}
    out = list(existing)
    p = PEOPLE.get(series_id)
    if not p:
        return out
    candidates = [p["name_jp"], p["name_en"], *p.get("aliases_en", []), *p.get("topics", [])]
    candidates += ["人物伝", "偉人伝", "ビジネス", "起業家", "biography"]
    for c in candidates:
        if c.lower() not in seen:
            out.append(c)
            seen.add(c.lower())
    # YouTube tag total <= 500 chars (incl. comma separators). Trim if needed.
    while out and sum(len(t) for t in out) + len(out) > 480:
        out.pop()
    return out


def _rewrite_description(existing: str, series_id: str, channel_id: str | None, kind: str) -> str:
    seo = _build_seo_block(series_id, channel_id, kind)
    if MARKER in existing:
        lead = existing.split(MARKER, 1)[0].rstrip()
    else:
        # Strip existing trailing hashtag-only paragraph (the old style)
        lines = existing.rstrip().splitlines()
        while lines and lines[-1].strip().startswith("#"):
            lines.pop()
        # also strip the now-trailing blank line
        while lines and not lines[-1].strip():
            lines.pop()
        lead = "\n".join(lines)
    return lead + seo


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", required=True, help="channels.id (e.g. ijinden_ja)")
    ap.add_argument("--kind", choices=["short", "long"], default=None)
    ap.add_argument("--series", default=None, help="restrict to one series_id")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--client-secret", type=Path, default=DEFAULT_CLIENT_SECRET)
    ap.add_argument("--token", type=Path, default=None,
                    help="explicit token path; defaults to the channel's registered token")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--limit", type=int, default=None, help="cap number of updates")
    args = ap.parse_args()

    token = args.token or resolve_channel_token(args.channel)
    creds = get_credentials(args.client_secret, token, args.port)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    with connect() as conn, conn.cursor() as cur:
        sql = """
          SELECT video_id, series_id, kind, title, description, tags, category_id
          FROM videos
          WHERE channel_id = %s
            AND superseded_by IS NULL
            AND (metadata->>'deleted_at') IS NULL
        """
        params: list = [args.channel]
        if args.kind:
            sql += " AND kind = %s"; params.append(args.kind)
        if args.series:
            sql += " AND series_id = %s"; params.append(args.series)
        sql += " ORDER BY uploaded_at"
        if args.limit:
            sql += " LIMIT %s"; params.append(args.limit)
        cur.execute(sql, params)
        rows = cur.fetchall()

    print(f"=== {len(rows)} videos to update  (channel={args.channel} dry_run={args.dry_run}) ===")
    updated = 0
    for vid, series_id, kind, title, desc, tags, category_id in rows:
        new_desc = _rewrite_description(desc or "", series_id, args.channel, kind)
        new_tags = _build_tags(series_id, tags)
        if new_desc == desc and new_tags == (tags or []):
            print(f"  [{vid}] no change")
            continue

        print(f"\n[{vid}] {title}")
        print(f"  --- new description ({len(new_desc)} chars) ---")
        for ln in new_desc.splitlines():
            print(f"    {ln}")
        print(f"  --- new tags ({len(new_tags)}) ---")
        print(f"    {new_tags}")
        if args.dry_run:
            continue

        snippet = {
            "title": title,
            "description": new_desc,
            "categoryId": str(category_id or "22"),
            "tags": new_tags,
        }
        try:
            youtube.videos().update(
                part="snippet",
                body={"id": vid, "snippet": snippet},
            ).execute()
            updated += 1
            print("  ✓ updated")
            time.sleep(0.1)  # be polite
        except HttpError as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            return 1

    print(f"\n=== updated {updated} / {len(rows)} ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
