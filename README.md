# claude-code-gen-shorts

**Claude Code に日本語で「作って」と言うだけで、ショート動画が生成され YouTube にアップロードされるリポジトリです。**

絵を描く・ナレーション音声を作る・字幕や効果音つきで動画に合成する・YouTube に上げる・再生数を集計する —— **面倒なところは全部 Claude Code がやります**。あなたがやるのは、**最初のインストールと認証**、そして **テーマを決めてシナリオに OK を出す** ことだけ。

そしてもう一つ大事なこと —— これは完成品のツールではありません。**ソースを自由に書き換えて、「動画の作り方」そのものを各自が変えて使うための土台**です。

> 🤖 このリポジトリは [Claude Code](https://docs.claude.com/en/docs/claude-code) と一緒に使う前提で設計されています。Claude 向けの操作説明は [`CLAUDE.md`](CLAUDE.md) にあります。
>
> 🖥️ 勉強会スライド: **https://petertakahashi.github.io/claude-code-gen-shorts/**

---

## 誰が何をやるのか

| 👤 人がやること（これだけ） | 🤖 Claude がやること（頼むだけ） |
|---|---|
| ① 最初に Claude Code を入れる | シナリオを書く |
| ② 認証まわりの初期設定（APIキー / YouTube・GCP の OAuth） | イラストを生成する |
| ③ テーマを決めて、シナリオに OK を出す | ナレーション音声を作る |
| | 字幕・効果音つきで動画に合成する |
| | YouTube にアップロードする |
| | 再生数を集計して分析できる状態にする |

手を動かす必要があるのは **「最初の導入」と「認証」** だけ。それが済めば、あとは会話で回ります。

---

## どんな動画ができるか

実際に運用しているチャンネルから（サムネをクリックすると動画が開きます）。

| | 動画 | 再生数 |
|---|---|---:|
| [![](https://img.youtube.com/vi/LZBgDaeRwcU/hqdefault.jpg)](https://youtube.com/shorts/LZBgDaeRwcU) | [1990円フリースで社会現象を起こした男](https://youtube.com/shorts/LZBgDaeRwcU) | 8,832 |
| [![](https://img.youtube.com/vi/BfcNnLQDvv0/hqdefault.jpg)](https://youtube.com/shorts/BfcNnLQDvv0) | [刑務所で1000冊読んだ男](https://youtube.com/shorts/BfcNnLQDvv0) | 5,198 |
| [![](https://img.youtube.com/vi/AdqXXJzcSN4/hqdefault.jpg)](https://youtube.com/shorts/AdqXXJzcSN4) | [カモノハシは、生物学の常識を全部破る動物](https://youtube.com/shorts/AdqXXJzcSN4) | 5,104 |
| [![](https://img.youtube.com/vi/lT05IM-V5Y0/hqdefault.jpg)](https://youtube.com/shorts/lT05IM-V5Y0) | [ドイツ人観光客が日本のトイレで泣いた理由](https://youtube.com/shorts/lT05IM-V5Y0) | 4,353 |
| [![](https://img.youtube.com/vi/x7NvYVZbPEY/hqdefault.jpg)](https://youtube.com/shorts/x7NvYVZbPEY) | [ニュース系ショート（実写アバター + 日付バッジ）](https://youtube.com/shorts/x7NvYVZbPEY) | — |

**実績（2026-06-07 時点）**

- **32 チャンネル / 281 本 / 累計 339,000 再生 / 3,699 いいね**
- 1本あたりの費用 ＝ **$0.20 程度**（画像生成だけ。音声・アップロードは無料）
- 1本あたりの手間 ＝ **10分弱**（テーマ決め＋OK出し＋確認）

---

## 仕組み（ざっくり）

```
  あなた：「○○のショートを作って」
            │
            ▼
   ┌──────────────────────────────┐
   │           Claude Code          │   ← 自然言語で指示するだけ
   └──────────────────────────────┘
       │       │        │         │
       ▼       ▼        ▼         ▼
    シナリオ  イラスト  ナレーション   動画に合成
              生成      音声生成     (字幕・効果音)
                                       │
                                       ▼
                             できあがった縦動画
                                       │
                                       ▼
                         YouTube に自動アップロード
                                       │
                                       ▼
                       再生数を集計 → ダッシュボードで分析
```

中身は普通の Python のソースコードです。気に入らなければ、Claude に「ここをこう直して」と言えば書き換わります。

---

## セットアップ

### ① まず動かす

```bash
# 1. Claude Code を入れる（人がやる初回作業）
npm i -g @anthropic-ai/claude-code

# 2. このリポジトリを取ってくる
git clone https://github.com/PeterTakahashi/claude-code-gen-shorts
cd claude-code-gen-shorts

# 3. Claude Code を起動（初回はブラウザでログイン）
claude
```

起動したら、あとは日本語で頼むだけです。依存パッケージのインストール（`uv sync` / ffmpeg など）も「環境を整えて」と頼めばやってくれます。

### ② 画像と音声

| やること | 内容 |
|---|---|
| **画像** | [aistudio.google.com](https://aistudio.google.com/apikey) で `GEMINI_API_KEY` を無料発行 → `.env.example` をコピーして `.env` を作り、貼る |
| **音声** | [Aivis Speech](https://hub.aivis-project.com/)（日本語TTS・無料）をダウンロードしてローカル起動。立ち上げておくと Claude がそこに喋らせて音声を作る |
| **指示書** | ジャンル別の「作り方」(Skill) はリポジトリに同梱済み。`/biography-webtoon` のように `/` で呼べます |

ここまでで「動画を作る」ところまで動きます。**アップロードしたい人だけ ③ へ。**

### ③ YouTube に上げる（認証）

一番手間なのがここですが、**最初に1回だけ**です。すべて [Google Cloud Console](https://console.cloud.google.com/) で行います。**画面の文言は時期によって変わる**ので、迷ったらこの節をそのまま Claude に貼って「この通りに案内して」と頼んでください。

#### 1. プロジェクトを作って API を有効化

1. Console 左上のプロジェクト選択 → **新しいプロジェクト**（名前は何でも可）
2. 検索バーで「**YouTube Data API v3**」→ **有効にする**
3. （再生数の分析もするなら）同様に「**YouTube Analytics API**」も有効化

#### 2. OAuth 同意画面を作る

1. 「**API とサービス → OAuth 同意画面**」
2. User Type = **外部（External）** → 作成
3. アプリ名・サポートメール・デベロッパー連絡先を入力（個人利用なので適当でOK）
4. **スコープ**で次の3つを追加（このリポジトリが使うもの）:
   - `.../auth/youtube.upload`
   - `.../auth/youtube`
   - `.../auth/yt-analytics.readonly`
5. **テストユーザー**に **自分の Google アカウント（アップ先チャンネルの持ち主）を必ず追加**
   - ⚠️ ここを忘れると認証時に「**アクセスをブロックしました: このアプリは Google の審査プロセスを完了していません**」で必ず止まります。公開（本番）にする必要はなく、**テストのまま**で動きます。

#### 3. OAuth クライアント ID を作る（← リダイレクト URI の注意点）

「**API とサービス → 認証情報 → 認証情報を作成 → OAuth クライアント ID**」

ここで **アプリの種類** を選びます。**2通りあり、どちらでも動きますが扱いが違います**:

| 種類 | リダイレクト URI の登録 | おすすめ |
|---|---|---|
| **デスクトップアプリ** | **不要**（loopback が自動で許可される） | ✅ こちらが簡単 |
| **ウェブ アプリケーション** | **必須**（下記） | 既にこちらで作った人向け |

> 🚨 **「ウェブ アプリケーション」を選んだ場合は、必ず次を登録してください**（ここが README で一番つまずく所です）。
>
> **「承認済みのリダイレクト URI」に、末尾スラッシュ込みでこの1行を必ず追加:**
>
> ```
> http://localhost:8080/
> ```
>
> このリポジトリの認証コードは `run_local_server(port=8080)` で **`http://localhost:8080/` にコールバックを受ける**ため、これが登録されていないと認証画面で
> **`Error 400: redirect_uri_mismatch`** になって先へ進めません。
> `http://127.0.0.1:8080/` ではなく **`localhost`**、かつ **末尾の `/` まで**完全一致が必要です。
> （別ポートを使いたいときは upload コマンドに `--port <番号>` を渡し、ここの URI も同じ番号で登録してください。）

作成すると **JSON をダウンロード**できます。それを **リポジトリ直下** に、次の名前のまま置きます（`.gitignore` 済みなのでコミットされません）:

```
client_secret_xxxxxxxx.apps.googleusercontent.com.json
```

#### 4. 初回だけブラウザで認証

アップ先の **YouTube チャンネル**を用意したうえで、アップロードを1回実行するとブラウザが開きます（例）:

```bash
PYTHONUNBUFFERED=1 .venv/bin/python -m src.youtube_batch_upload_shorts <project> \
  --only <short_id> --privacy private
```

- ブラウザでアカウントを選び（**テストユーザーに入れたアカウント**）、警告画面は「**続行**」→ スコープを許可
- 成功すると `http://localhost:8080/` に自動で戻り、トークンが **`.youtube_token.json`**（チャンネル指定時は `.youtube_token.<channel>.json`）に保存されます
- **2回目以降はこの保存トークンで自動**。＝ 認証が終われば、もう手作業はほぼゼロです。

> 詳しいコマンド・複数チャンネル運用・quota 昇格申請は [`CLAUDE.md`](CLAUDE.md) の §8 を参照（Claude に「YouTube 認証をセットアップして」と頼んでも案内してくれます）。

---

## 動画の作り方（実際の会話）

```
あなた ＞ 動物雑学チャンネルに、ハチドリの面白いショートを作って

Claude ＞ シナリオ案です（6パネル構成）
          1. 掴み：ハチドリは1秒に50回羽ばたく…
          …
          6. オチ：実は…
          これで進めていい？

あなた ＞ OK。3番をもっと意外な事実に変えて

Claude ＞ 修正しました。では生成します
          → イラスト6枚 生成 → ナレーション音声 合成
          → 字幕・効果音つきで動画に合成 → YouTube にアップロード 完了
          https://youtube.com/shorts/xxxxxxxx
```

人の操作は **「作って」** と **「OK」** の2回だけです。

---

## このリポジトリの目的：自由に改変して使う

完成品を配るのではなく、**みんなが自分用に改造する土台**として置いています。

- **絵柄・尺・構成・字幕ルール** — ジャンルごとの指示書（`.claude/skills/` の Skill）を書き換えれば変わる
- **新ジャンル** — Skill を1つ足せば、新しいチャンネルが立ち上がる
- **画像・音声エンジン** — 別のものに差し替えてもいい
- 気に入らない挙動は、**Claude に「ここをこう直して」と言えばソースごと変わる**

同梱の Skill（`/` で呼べる作り方のテンプレ）:

| Skill | 役割 |
|---|---|
| `/biography-webtoon` | 偉人伝（アニメ調・人物の人生を圧縮） |
| `/news-shorts` | ニュース系（実写・アバター冒頭・日付バッジ） |
| `/youtube-shorts` | 汎用ショート（テーマ自由） |
| `/cautionary-tale-webtoon` | 失敗談（住宅・お金・美容などの「後悔→回避法」） |
| `/novel-to-webtoon` | 既存小説の縦スクロール webtoon 化 |
| `/webtoon-scenario-design` | パネル設計のルール集 |

---

## 拡張：Skills と Playwright / MCP（すぐ使えるように）

### Skills（同梱済み・追加インストール不要）

ジャンル別の「作り方」(Skill) は `.claude/skills/` に**コミット済み**です。**clone して `claude` を起動すればそのまま使えます。**

```text
# 呼び出し方（どちらでもOK）
/biography-webtoon                        # スラッシュで直接呼ぶ
偉人伝チャンネルでジョブズのショート作って    # 自然言語。Claude が該当 Skill を自動で読む
```

自分の Skill を足したいときは `.claude/skills/<名前>/SKILL.md` を作るだけ（先頭に `name` と `description` の frontmatter）。次回起動時に Claude が認識します。

### Playwright（YouTube quota 回避 / ニュース記事取得に使用）

このリポの `tools/yt_pw_*.py`（YouTube Studio 経由アップロード = **API quota 消費 0**）や `tools/news_fetch.py`（日経 / Bloomberg のログイン記事取得）は、**Python の Playwright** を使います。

```bash
# Claude に「playwright をセットアップして」と頼めば下記をやってくれる
uv pip install playwright          # または: pip install playwright
playwright install chromium        # ブラウザ本体を入れる

# 初回だけログイン状態を作る（cookie をプロファイルに保存。以後は自動）
.venv/bin/python tools/yt_pw_login.py
```

### （任意）Playwright MCP — Claude に直接ブラウザを操作させたい場合

上の Python ツールとは別に、**Claude 自身がブラウザを操作できる Playwright MCP** を足すこともできます（「このページ開いてスクショ取って」等を直接実行）。動画生成そのものには必須ではありません。

```bash
# このプロジェクトに追加（-s project で .mcp.json に書かれ、clone した人にも共有される）
claude mcp add playwright -s project -- npx @playwright/mcp@latest

# 確認
claude mcp list
```

---

## 使っている技術（差し替え可能）

| 役割 | デフォルト | メモ |
|---|---|---|
| 画像生成 | Gemini 2.5 Flash Image (nanobanana) | $0.039/枚、Batch で 50% off。安定・速い |
| 日本語音声 | Aivis Speech（ローカル・無料） | 英語は Kokoro、その他言語は Qwen3-TTS |
| 動画合成 | ffmpeg | 字幕焼き付け・効果音ミックス |
| アップロード | YouTube Data API v3 | quota 超過時は Playwright 経由でフォールバック |
| 分析 | PostgreSQL + Redash（docker） | 再生数を日次同期して可視化 |
| ニュース系の冒頭アバター（任意） | HeyGen Photo Avatar | 5秒のトーキングヘッド |

---

## ライセンス / 注意事項

- このリポジトリは **MIT** ライセンスです（`LICENSE` 参照）。
- 下記は **ユーザー個別の責任** で取得・運用してください:
  - YouTube API quota、Gemini / OpenAI / HeyGen などの課金
  - 著作権を含む素材（実在人物の写真、企業ロゴ、報道記事の引用）
  - YouTube のコミュニティ / Shorts ガイドライン
- AI は "それっぽいけど事実でない" 出力を出すことがあります。内容の **事実性はユーザー側で必ず検証**してください。
- `.env` / `.youtube_token.*.json` / `client_secret_*.json` は `.gitignore` 済みです。**push 前に必ず `git status` で混入を確認**してください。
