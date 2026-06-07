# webtoon-gen — Claude Code で動かす YouTube Shorts 量産パイプライン

YAML 1枚で **30秒の縦型ショート動画 (1080×1920, 9:16)** を生成し、複数の YouTube チャンネルへ自動アップロードまで行うパイプラインです。
偉人伝・日本礼賛・動物雑学・スポーツ・宇宙・倒産企業・事件・物理・数学・恋愛科学・ニュース速報 など、計 **32 チャンネル / 281 本 / 累計 339,000 再生超** の実運用で叩かれています (2026-06-07 時点)。

すべての面倒なところ ── 画像生成・TTS・字幕焼き付け・SFX 合成・ffmpeg 連結・サムネ生成・YouTube API アップ ── は Claude Code が、Skill 経由で自然言語の指示から駆動します。

> 🤖 このリポジトリは [Claude Code](https://docs.claude.com/en/docs/claude-code) と使うことを前提に設計されています。

---

## 何ができるか

### 1. 偉人伝ショート (anime / photoreal)

歴史上の人物や現代の起業家の人生を 30 秒に圧縮。`projects/<biography_id>/shorts/<sid>.yaml` を 1 枚書けば、パネル画像生成 → ナレーション → 字幕合成 → ffmpeg → YouTube アップまで自動。

| | 動画 | 再生数 |
|---|---|---:|
| [![](https://img.youtube.com/vi/LZBgDaeRwcU/hqdefault.jpg)](https://youtube.com/shorts/LZBgDaeRwcU) | [1990円フリースで社会現象を起こした男](https://youtube.com/shorts/LZBgDaeRwcU) | 8,832 |
| [![](https://img.youtube.com/vi/BfcNnLQDvv0/hqdefault.jpg)](https://youtube.com/shorts/BfcNnLQDvv0) | [刑務所で1000冊読んだ男](https://youtube.com/shorts/BfcNnLQDvv0) | 5,198 |
| [![](https://img.youtube.com/vi/sk4yIMNGgFs/hqdefault.jpg)](https://youtube.com/shorts/sk4yIMNGgFs) | [ジョブズが風呂に入らなかった本当の理由](https://youtube.com/shorts/sk4yIMNGgFs) | 3,873 |
| [![](https://img.youtube.com/vi/Ue208wS47P8/hqdefault.jpg)](https://youtube.com/shorts/Ue208wS47P8) | [羽生結弦、ケガを越えて五輪連覇した男](https://youtube.com/shorts/Ue208wS47P8) | 3,857 |
| [![](https://img.youtube.com/vi/kI23b5-hBK0/hqdefault.jpg)](https://youtube.com/shorts/kI23b5-hBK0) | [イチローが毎朝、同じ時間にカレーを食べた理由](https://youtube.com/shorts/kI23b5-hBK0) | 4,171 |

### 2. ニュース系ショート (実写, HeyGen アバター + 日付バッジ)

日経 / Bloomberg / CoinPost / X の API から最新トピックを取得 → 12 パネルで構成 → Aivis で 1.25× の速いナレーション → HeyGen の写真アバターで 5 秒のトーキングヘッドを冒頭に挿入。`MM/dd` の日付バッジが常時右上。

| | 動画 | チャンネル |
|---|---|---|
| [![](https://img.youtube.com/vi/x7NvYVZbPEY/hqdefault.jpg)](https://youtube.com/shorts/x7NvYVZbPEY) | [三菱重工社長「ナフサ不足が工場の潤滑油に直撃」](https://youtube.com/shorts/x7NvYVZbPEY) | バルトゥーン株式ニュース |
| [![](https://img.youtube.com/vi/cTh5sf3lDMI/hqdefault.jpg)](https://youtube.com/shorts/cTh5sf3lDMI) | [AIデータセンターは「水で冷やす」](https://youtube.com/shorts/cTh5sf3lDMI) | バルトゥーンテックニュース |
| [![](https://img.youtube.com/vi/zmxWkJ9NKzI/hqdefault.jpg)](https://youtube.com/shorts/zmxWkJ9NKzI) | [出産費用ゼロへ、改正健康保険法が成立](https://youtube.com/shorts/zmxWkJ9NKzI) | バルトゥーン政治ニュース |

### 3. 雑学・動物・宇宙・歴史など

| | 動画 | 再生数 |
|---|---|---:|
| [![](https://img.youtube.com/vi/AdqXXJzcSN4/hqdefault.jpg)](https://youtube.com/shorts/AdqXXJzcSN4) | [カモノハシは、生物学の常識を全部破る動物](https://youtube.com/shorts/AdqXXJzcSN4) | 5,104 |
| [![](https://img.youtube.com/vi/oc69LKDHjcE/hqdefault.jpg)](https://youtube.com/shorts/oc69LKDHjcE) | [タコは心臓が3つ脳が9つの生き物だった](https://youtube.com/shorts/oc69LKDHjcE) | 4,843 |
| [![](https://img.youtube.com/vi/lT05IM-V5Y0/hqdefault.jpg)](https://youtube.com/shorts/lT05IM-V5Y0) | [ドイツ人観光客が日本のトイレで泣いた理由](https://youtube.com/shorts/lT05IM-V5Y0) | 4,353 |
| [![](https://img.youtube.com/vi/aSznzIPUGjQ/hqdefault.jpg)](https://youtube.com/shorts/aSznzIPUGjQ) | [日本で財布を落とした外国人が、震えた理由](https://youtube.com/shorts/aSznzIPUGjQ) | 4,329 |

### 実績ハイライト (2026-06-07 時点)

- **32 チャンネル / 281 本 / 累計 339,000 再生 / 3,699 いいね**
- 偉人伝チャンネル: 74 本 / 75,000 再生
- 日本礼賛チャンネル: 16 本 / 43,000 再生 (1本あたり 2,700 再生 = like率 15.6 per 1k views)
- 単発トップは **8,832 再生** (柳井正・ユニクロ創業)

| Rank | チャンネル | 本数 | 累計views | 累計likes |
|---:|---|---:|---:|---:|
| 1 | 偉人伝 | 74 | 74,956 | 416 |
| 2 | バルトゥーン日本礼賛 | 16 | 43,096 | 672 |
| 3 | バルトゥーン動物雑学 | 13 | 27,910 | 446 |
| 4 | バルトゥーンスポーツ選手伝説 | 12 | 27,015 | 191 |
| 5 | バルトゥーン宇宙 | 13 | 22,945 | 293 |
| 6 | バルトゥーン倒産企業 | 14 | 20,316 | 202 |

---

## アーキテクチャ

```
   YAML 1枚 (パネルプロンプト + ナレーション)
        │
        ▼
┌─────────────────────────────────────────┐
│ src/short_gen.py — メインパイプライン        │
└─────────────────────────────────────────┘
   │       │           │            │
   ▼       ▼           ▼            ▼
[Gemini 2.5  [Aivis    [ElevenLabs  [ffmpeg
 Flash      日本語TTS    SFX 合成     合成・字幕焼き付け]
 Image]     ローカル]   (任意)]
                                      │
                                      ▼
                            output/shorts/<sid>/ja/short.mp4
                                      │
                                      ▼
┌─────────────────────────────────────────┐
│ src/youtube_batch_upload_shorts.py     │
│ → YouTube Data API でチャンネルへ public 投稿  │
└─────────────────────────────────────────┘
                                      │
                                      ▼
                            PostgreSQL (videos / video_stats)
                                      │
                                      ▼
                    Redash で日次 stats sync + 可視化
```

### ニュース系のときの追加スタック

- **HeyGen** Photo Avatar API — 5秒のトーキングヘッドを冒頭に貼り付け
- **news_fetch.py** — Nikkei / Bloomberg / CoinPost の本文を Playwright ログイン状態で取得
- **x_trending.py** — X API v2 で `@nikkei` `@BloombergJapan` `@coin_post` から high-engagement headline を抽出
- **news_image_ref.py** — Bing 画像検索で参照画像を取得 → nanobanana へリファレンスとして渡し、著作権セーフな「描き直し」を実現

---

## 必要なもの

| 必須 | バージョン | 備考 |
|---|---|---|
| Python | 3.12+ | `uv` 推奨 |
| Docker / Docker Compose | — | PostgreSQL (port 5433) + Redash (port 5001) を立てる |
| ffmpeg | 6+ | Homebrew で `brew install ffmpeg` |
| **Aivis Speech** | latest | 日本語TTS、ローカル起動 (port 10101)。https://hub.aivis-project.com/ から取得 |
| Claude Code CLI | latest | `npm i -g @anthropic-ai/claude-code` |

| 必須API キー | 取得場所 | 用途 |
|---|---|---|
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey | パネル画像生成 (nanobanana) |
| YouTube Data API v3 | GCP コンソール → API有効化 + OAuth client | Shorts アップロード |

| 任意API キー | 用途 |
|---|---|
| `HEYGEN_API_KEY` | ニュース系のアバター動画 (https://app.heygen.com) |
| `OPENAI_API_KEY` | 英語TTS (Kokoro 代替) など |
| `ELEVENLABS_API_KEY` | 冒頭SFX |
| X (Twitter) API v2 Bearer Token | ニュース取得 (`x_trending.py`) |
| 日経電子版 / Bloomberg ログイン | 記事本文取得 (Playwright プロファイル経由) |

---

## クイックスタート

```bash
# 1. clone & 依存インストール
git clone https://github.com/<your-account>/webtoon-gen.git
cd webtoon-gen
uv sync                                # or python -m venv .venv && pip install -e .

# 2. .env を作る
cp .env.example .env                   # 自分のAPIキーを書く

# 3. Aivis Speech をローカル起動 (別ターミナル)
#    https://hub.aivis-project.com/ からダウンロード→起動
#    listening on http://127.0.0.1:10101

# 4. PostgreSQL + Redash を docker で立ち上げ
docker compose up -d postgres

# 5. Claude Code を起動
claude

# 6. プロンプトに以下を入力:
#    「偉人伝チャンネル用にスティーブ・ジョブズのカリグラフィの講義のショートを作って」
#    → Claude が biography-webtoon skill を起動し、yaml→生成→確認まで案内
```

---

## YouTube Data API v3 を有効化する手順

1. https://console.cloud.google.com/ で新規プロジェクト作成
2. 「APIとサービス」→「ライブラリ」→ **YouTube Data API v3** を有効化
3. 「APIとサービス」→「OAuth同意画面」を **External / テストモード** で作成。スコープに以下を追加:
   - `https://www.googleapis.com/auth/youtube.upload`
   - `https://www.googleapis.com/auth/youtube.readonly`
   - `https://www.googleapis.com/auth/yt-analytics.readonly` (statsで dislikes を取りたい場合)
4. テストユーザーに自分の Google アカウントを追加
5. 「認証情報」→ **OAuth 2.0 クライアントID** を **デスクトップアプリ** で作成 → JSON を `client_secret_*.apps.googleusercontent.com.json` としてリポジトリ直下に保存
6. quota の昇格申請を出す (デフォルト 10,000 unit/day では1日6本までしかupできない)。50,000 unit まで昇格申請が通りやすい。

> 💡 1 動画 upload = 1,600 units + thumbnail 50 units。元の 10,000 quota だと **1日約 6 本**。50,000 まで昇格すれば **1日約 30 本**。詳細は `src/youtube_batch_upload_shorts.py` を参照。

---

## ショート動画を 1 本作る最小フロー

### A. YAML を書く

```yaml
# projects/stevejobs/shorts/jobs-calligraphy.yaml
id: jobs-calligraphy
parent_chapter: null
panels:
  - id: p1
    prompt: |
      A 9:16 vertical anime/webtoon style illustration of Steve Jobs as a
      Reed College dropout sitting in a calligraphy class in 1972, ...
  - id: p2
    prompt: |
      ...
ja:
  title: 'ジョブズが大学で受けた、たった一つの講義 #Shorts'
  description: |
    1972年、リード大学を中退したスティーブ・ジョブズは、聴講生として
    カリグラフィの授業を受け続けた。十年後、その経験が初代Macに「世界で最も
    美しい書体」を生み出すことになる。30秒で解説します。

    #Shorts #偉人伝 #スティーブジョブズ
  hook_caption: ジョブズが大学で受けた一つの講義
  series_brand: スティーブ・ジョブズ
  voice_speed: 1.4
  narration:
    - panel: p1
      text: 1972年、リード大学を中退したジョブズは、不思議な選択をします。
      caption: 大学中退後、不思議な選択
    - panel: p2
      text: ...
      caption: ...
```

### B. パイプラインを走らせる

```bash
# 画像生成 + TTS + ffmpeg → output/shorts/<sid>/ja/short.mp4
.venv/bin/python -m src.short_gen stevejobs jobs-calligraphy
```

### C. YouTube へアップロード

```bash
# プロジェクト + チャンネル + sid を指定
.venv/bin/python -m src.youtube_batch_upload_shorts stevejobs \
  --channel ijinden_ja \
  --only jobs-calligraphy \
  --privacy public
# → 初回はブラウザでOAuth認証 → .youtube_token.ijinden.json に保存
# → 2回目以降はトークン自動利用
```

### D. Claude Code に丸投げ (推奨)

`/biography-webtoon` または `/news-shorts` のスキルが用意されているので、Claude Code を起動して自然言語で指示するだけ。

```
あなた> 偉人伝チャンネルでスティーブ・ジョブズのカリグラフィのショートを作って、
        できたら本番にアップして
Claude> （調べ物 → yaml 生成 → short_gen 実行 → 確認用 mp4 をユーザーに送付 →
         OKをもらってから ijinden_ja に upload）
```

---

## 主な Skill / コマンド一覧

| Skill | 役割 |
|---|---|
| `/biography-webtoon` | 偉人伝 (anime, 6パネル, 1.4×) |
| `/news-shorts` | ニュース系 (photoreal, 12パネル, 1.25×, HeyGen アバター + 日付バッジ) |
| `/youtube-shorts` | 汎用ショート (テーマ自由) |
| `/cautionary-tale-webtoon` | 失敗談 (住宅ローン地獄など、広告枠に転用しやすい7ビート構成) |
| `/novel-to-webtoon` | 既存小説の縦スクロール webtoon 化 |
| `/webtoon-scenario-design` | パネル設計の規則集 (吹き出し位置・shot grammar など) |

| 直接コマンド | 説明 |
|---|---|
| `python -m src.short_gen <proj> <sid>` | 1本生成 |
| `python -m src.short_gen <proj> --all --batch` | プロジェクト内全部を Gemini Batch (50% off) で生成 |
| `python -m src.youtube_batch_upload_shorts <proj> --channel <ch> --only <sid>` | 1本アップロード |
| `python -m src.youtube_stats_sync` | 全動画の views/likes/comments を DB に同期 |
| `python tools/sync_anchor_opener.py --backend heygen --short <mp4>` | ニュース動画の冒頭にトーキングヘッドを貼る |
| `python tools/news_fetch.py <URL> --out /tmp/x.json` | 日経/Bloomberg 記事本文を取得 |
| `python tools/x_trending.py --accounts BloombergJapan nikkei --hours 24` | X からトレンド見出しを取得 |

---

## 画像生成: 何を使うのが正解か

| バックエンド | コスト | 品質 | 速度 | 結論 |
|---|---|---|---|---|
| **Gemini 2.5 Flash Image (nanobanana)** | $0.039/枚 (Batch 50% off で $0.020) | ◎ 安定 | ◎ 速い | **推奨デフォルト**。リファレンス画像対応で本人写真も渡せる |
| OpenAI gpt-image-1 (ChatGPT) | $0.04-0.17/枚 | ○ | △ | 代替として使える。`src/image_generator.py` 改造で切替可 |
| FLUX.2 ローカル (MLX) | 無料 | △ 品質不足 | ◎ | **2026-05に試して却下**。QA工数が増えて結局 nanobanana のほうがTCO低い |
| LTX-2.3 / Wan2.2 など i2v | 無料 | × 容量重い | △ | 試したが品質不足、static panel 維持で十分 |

**結論: 月数百〜数千枚程度なら nanobanana が圧倒的にコスパ良い** (32ch運用でも月 $20-50 程度)。

---

## TTS: 言語別の推奨

| 言語 | エンジン | port | 備考 |
|---|---|---|---|
| 日本語 | **Aivis Speech** | 10101 | ローカル、無料、自然。誤読は `tools/aivis_userdict.py` で辞書登録 |
| 英語 | Kokoro-82M | 10103 | ローカル、無料 |
| 他言語 | Qwen3-TTS | 10102 | 多言語対応 |
| (任意) | ElevenLabs | — | SFX のみ。冒頭の爆発音・チャイムなど |

---

## ハマりどころ / FAQ

- **YouTube API quota が枯渇**: 1日 50,000 units = 約 30 本。超えたら `tools/yt_pw_upload.py` (Playwright 経由、quota 0) でフォールバック。reset は **15:00 JST**。
- **Gemini が「no image returned」を出す**: コンテンツポリシー (実在人物の顔・ロゴ・暴力描写) に引っかかった可能性。プロンプトを抽象化 + 「No real logos」明記で回避。
- **Aivis の誤読**: 「起業家 → きぎょういえ」「羽生さん → ハブさん」など複合語の分割ミスがある。`tools/aivis_userdict.py` に登録 → 該当 seg_NN.mp3 + `output/.../narration.mp3` + `narration_with_sfx.mp3` を削除 → 再生成。
- **再生成しても動画に反映されない**: `output/shorts/<sid>/ja/narration.mp3` と `narration_with_sfx.mp3` が concat キャッシュとして残るため、これらも削除する必要がある。

---

## ライセンス / 注意事項

- このリポジトリは **MIT** ライセンスです (LICENSE 参照)。
- ただし下記は **ユーザー個別の責任** で取得・運用してください:
  - YouTube API quota、HeyGen クレジット、Gemini / OpenAI 課金
  - 著作権を含む素材 (実在人物の写真、企業ロゴ、報道記事の引用)
  - YouTube の Shorts ガイドラインおよびコミュニティガイドライン
- 自動生成された動画でも、内容の **事実性** はユーザー側で検証してください。AI が "それっぽいけど事実でない" 出力を出すケースがあります。
- `.env` および `.youtube_token.*.json`、`client_secret_*.json` は `.gitignore` 済み。**push 前に必ず `git status` で混入を確認してください**。

---

## クレジット

- Claude Code (Anthropic) — オーサリングとオーケストレーションの中核
- Gemini 2.5 Flash Image (Google) — パネル画像生成
- Aivis Speech — 日本語 TTS
- HeyGen — Photo Avatar
- nikkei.com / bloomberg.co.jp / coinpost.jp — ニュース系の事実ソース
