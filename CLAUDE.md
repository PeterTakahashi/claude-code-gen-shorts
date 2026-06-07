# CLAUDE.md — このリポジトリの操作ガイド（Claude 向け）

You are operating inside **claude-code-gen-shorts**, a pipeline that turns a one-file YAML into a 9:16 vertical YouTube Short (image generation → TTS → subtitles/SFX → ffmpeg → YouTube upload → stats). This file tells you **how to drive the code**. Genre-specific authoring rules live in `.claude/skills/`; read the matching skill before authoring a short.

ユーザーは基本的に **日本語の自然言語で「○○のショートを作って」** と頼んできます。あなたの仕事は、適切な Skill を選び、YAML を書き、パイプラインを回し、確認用 mp4 を見せ、OK をもらってからアップロードすることです。

---

## 0. まず最初に守ること

- **アップロードは必ず人の OK を取ってから。** 生成→確認用 mp4 をユーザーに送る→承認→アップ、の順。勝手に public で上げない。
- **実在人物・企業ロゴ・報道画像** はコンテンツポリシー / 著作権に注意。実写の本人顔は参照画像なしでは作らない（[[feedback_avoid_photoreal_for_real_people]] 方針）。
- **秘密情報をコミットしない。** `.env` / `.youtube_token.*.json` / `client_secret_*.json` は `.gitignore` 済み。push 前に `git status` で確認。
- **事実性。** ナレーションの事実は裏取りする。創作と事実を混ぜない。

---

## 1. リポジトリ地図

```
projects/<project_id>/          # 1チャンネル分の作業ディレクトリ
  ├─ project.yaml               # プロジェクト設定（言語・画風・チャンネル等）
  ├─ characters/ characters.yaml# キャラ設定とスタイルシート画像
  ├─ shorts/<short_id>.yaml     # ★ ショート1本の定義（panels + ja: narration）
  └─ output/ work/              # 生成物（.gitignore 済み・コミットしない）
       └─ shorts/<sid>/ja/short.mp4   # 完成動画

src/                            # パイプライン本体（下記「主要コマンド」参照）
tools/                          # ニュース取得・Playwrightアップ・TTS辞書など補助
.claude/skills/                 # ジャンル別の作り方（/で呼べる）
prompts/                        # LLM プロンプトのテンプレ
docs/index.html                 # 勉強会スライド（GitHub Pages で公開）
docker-compose.yml              # PostgreSQL(5433) + Redash(5001)
```

Python は **`uv` 管理**。実行は `.venv/bin/python -m src.<module>` または `uv run python -m src.<module>`。

---

## 2. Skill のルーティング（先に読む）

ユーザーの依頼内容で使う Skill を選び、**着手前にその SKILL.md を読む**こと。

| 依頼の例 | Skill |
|---|---|
| 「偉人/起業家の人生を動画に」「次の章を作って」 | `/biography-webtoon` |
| 「ニュースショート」「速報系」 | `/news-shorts` |
| 「○○のショート作って」（汎用） | `/youtube-shorts` |
| 「失敗談」「後悔」「住宅ローン地獄」 | `/cautionary-tale-webtoon` |
| 「小説を webtoon に」 | `/novel-to-webtoon` |
| パネル設計のルールが欲しい | `/webtoon-scenario-design` |

---

## 3. 標準ワークフロー（ショート1本）

1. **テーマ確認** — ユーザーの指定ジャンル・チャンネルを把握。曖昧なら聞く。
2. **リサーチ** — 事実を集める（ニュース系は §6 のツールで一次ソースを取得）。
3. **シナリオ作成** — `projects/<proj>/shorts/<sid>.yaml` を書く。構成は Skill の規則に従う。
   - **書く前にユーザーにシナリオ案（パネル割り＋ナレーション）を提示し、OK を取る。**
4. **生成** — `.venv/bin/python -m src.short_gen <proj> <sid>`
5. **確認** — 出力 `output/shorts/<sid>/ja/short.mp4` を `SendUserFile` で見せる。
6. **承認後アップロード** — `.venv/bin/python -m src.youtube_batch_upload_shorts <proj> --channel <ch> --only <sid> --privacy public`
7. **記録** — 必要なら stats sync（§5）。

---

## 4. YAML の最小スキーマ

`projects/<proj>/shorts/<sid>.yaml`:

```yaml
id: <short_id>
parent_chapter: null
panels:
  - id: p1
    prompt: |
      A 9:16 vertical anime/webtoon illustration of ...   # 画像生成プロンプト（英語）
  - id: p2
    prompt: |
      ...
ja:
  title: '... #Shorts'
  description: |
    ... 説明文 ...
    #Shorts #タグ
  hook_caption: 冒頭キャプション
  series_brand: 動画固有のシリーズ名     # チャンネル名ではなくトピック固有名詞
  voice_speed: 1.4                       # 偉人伝1.4 / ニュース1.25 が目安
  narration:
    - panel: p1
      text: ナレーション本文（Aivis が読む）
      caption: 画面下に焼く字幕
    - panel: p2
      text: ...
      caption: ...
```

既存の `projects/elonmusk/shorts/*.yaml` や `projects/<同ジャンル>/shorts/*.yaml` を**実例として必ず先に読む**こと。表記規則・字幕・吹き出し等のユーザー方針は recall されるメモリ（[[feedback_subtitle_conventions]] 等）に従う。

---

## 5. 主要コマンド

```bash
# --- 生成 ---
.venv/bin/python -m src.short_gen <proj> <sid>            # 1本生成
.venv/bin/python -m src.short_gen <proj> --all --batch    # 全部を Gemini Batch(50%off)で生成
.venv/bin/python -m src.short_gen <proj> <sid> --force     # キャッシュ無視で再生成
.venv/bin/python -m src.short_gen <proj> <sid> --language en  # 言語版（既存panel画像は再利用）

# --- アップロード ---
.venv/bin/python -m src.youtube_batch_upload_shorts <proj> --channel <ch> --only <sid> --privacy public
# 初回は <ch> ごとにブラウザOAuth → .youtube_token.<ch>.json に保存、以後自動

# --- 分析 ---
.venv/bin/python -m src.youtube_stats_sync                 # 全動画の views/likes を DB 同期
docker compose up -d postgres                              # DB（port 5433）
docker compose up -d                                       # Redash も（port 5001）
```

`short_gen` の主なフラグ: `--all --force --batch --language <ja|en> --speaker <name> --backend <auto|gemini|flux2-local>`（backend は **auto=gemini 固定**運用、[[project_flux2_local_backend]] により FLUX は廃止）。

---

## 6. ニュース系の追加ツール（`tools/`）

```bash
.venv/bin/python tools/x_trending.py --accounts BloombergJapan nikkei --hours 24   # トレンド見出し
.venv/bin/python tools/news_fetch.py <URL> --out /tmp/x.json                        # 記事本文（Playwrightログイン）
.venv/bin/python tools/news_image_ref.py ...                                        # 参照画像→nanobananaで描き直し
.venv/bin/python tools/sync_anchor_opener.py --backend heygen --short <mp4>         # 冒頭にHeyGenアバター
```

ニュース系は **1.25× ナレーション / 12+ パネル / 右上に MM/dd 日付バッジ / HeyGen 冒頭5秒**。詳細は `/news-shorts`。

---

## 7. ハマりどころ（これは毎回踏む）

- **TTS を直したのに動画に反映されない** → `seg_NN.mp3` だけでなく `output/shorts/<sid>/ja/narration.mp3` と `narration_with_sfx.mp3`（concat キャッシュ）も削除して再生成（[[feedback_tts_narration_mp3_cache_trap]]）。
- **Aivis の誤読**（複合語の誤分割・人名）→ `tools/aivis_userdict.py` で辞書登録 or かな書換。該当 seg と上記キャッシュを消す（[[feedback_tts_readings]]）。
- **Gemini が "no image returned"** → 実在人物の顔・ロゴ・暴力でポリシー抵触の可能性。プロンプトを抽象化、"No real logos" 明記。
- **YouTube quota 超過**（≈30本/日、reset 15:00 JST）→ `tools/yt_pw_upload.py`（Playwright・quota 0）でフォールバック（[[project_playwright_youtube_upload]]）。
- **GEMINI_API_KEY がシェル環境で上書き**される問題 → [[env_gemini_api_key_shadowed]]。
- **OAuth 用 Python を起動するとき** → `PYTHONUNBUFFERED=1` を付ける（認証URLを見るため）。

---

## 8. YouTube Data API v3 のセットアップ（人に案内する内容）

1. GCP で新規プロジェクト → **YouTube Data API v3 を有効化**（分析もするなら YouTube Analytics API も）
2. OAuth 同意画面（External / テスト）+ スコープ 3つ: `youtube.upload` `youtube` `yt-analytics.readonly`（`src/youtube_upload.py` の `SCOPES` と一致させること）
3. テストユーザーに自分の Google アカウントを追加（未追加だと「審査プロセス未完了」で認証がブロックされる）
4. **OAuth 2.0 クライアントID** を作成 → JSON を `client_secret_*.apps.googleusercontent.com.json` としてリポジトリ直下に保存
   - **デスクトップアプリ**で作るのが簡単（loopback 自動許可、リダイレクト URI 登録不要）。
   - ⚠️ **ウェブアプリケーション**で作る場合は **「承認済みのリダイレクト URI」に `http://localhost:8080/`（末尾スラッシュ込み・`localhost`）を必ず追加**。コードは `run_local_server(port=8080)` なので、未登録だと `redirect_uri_mismatch` で失敗する。別ポートは `--port` と URI を揃える。
5. quota 昇格申請（デフォルト 10,000 = 1日約6本、50,000 で約30本）
6. 初回アップロード時にブラウザ認証 → `http://localhost:8080/` に戻り `.youtube_token.<channel>.json` に保存

---

## 9. 環境メモ

- ポート: Aivis **10101**（日本語）/ Qwen3-TTS 10102（多言語）/ Kokoro 10103（英語）/ Postgres 5433 / Redash 5001。
- メインモデル/画像: 画像は nanobanana（Gemini 2.5 Flash Image）固定。多言語ショートは `i18n.en` を yaml に持たせて翻訳→英語TTS。
- 言語版を作るとき **panel 画像は再生成しない**（同 panels 共有、ナレーション順序変更のみ可・[[feedback_no_panel_regen_across_languages]]）。
- image-to-video / ローカル動画モデルは **不採用**（static panel 維持・[[feedback_no_i2v_for_now]] / [[project_ltx2_i2v_local]]）。
