# 小説 → Webtoon 動画 パイプライン

任意の小説を入力に、ナレーション・SFX・BGM 付きの縦スクロール webtoon 動画を出力するためのベスト構成。

---

## Skills (Claude Code)

このリポジトリには 2 つの Claude Skill が `.claude/skills/` に同梱されており、`claude -p` 起動時に自動で参照されます。

| Skill | 役割 | 呼ばれるタイミング |
|---|---|---|
| `webtoon-scenario-design` | webtoon/manga の視覚文法・コマ割り・吹き出し配置・擬音語ルールを集約。シナリオ生成の "正本" | S6 (scenes.json 生成) と S8 (bubbles.json 生成) で `claude -p` から明示的に invoke |
| `novel-to-webtoon` | このローカル pipeline の起動・stage 構成・トラブルシュートワークフロー | ユーザーが「webtoon を作って」「pipeline を回して」と頼んだとき、Claude 側で自動マッチ |

`prompts/decompose_scenes.md` と `prompts/author_bubbles.md` の冒頭で `webtoon-scenario-design` を Skill ツール経由で必ず読むよう指示してあります。

---

## 0. 前提

| 役割 | 採用 |
|---|---|
| OS | macOS |
| LLM (オーサリング) | Claude Code (`claude` CLI / SDK) |
| LLM (レビュー) | Codex |
| 画像生成 | nanobanana = Gemini 2.5 Flash Image。将来的に Stable Diffusion |
| 人声 TTS | **Aivis** (ローカル `http://127.0.0.1:10101`) |
| SFX / 環境音 | **ElevenLabs Sound Effects API** |
| 動画合成 | ffmpeg |
| 画像合成 (吹き出し) | Pillow |

ターゲット成果物:
- `output/<chapter>/webtoon.png` — 縦長 webtoon 1枚
- `output/<chapter>/webtoon_scroll.mp4` — hold-then-scroll の動画 (1080×1920)

---

## 1. 設計原則

1. **冪等性**: 各ステージは出力ファイル存在で skip する。`--force` で強制再生成。LLM で書く中間 JSON も同じ。
2. **人間レビューチェックポイント**: スクリプトが「次の手戻りポイント」まで自動で進み、レビューが要るところで停止メッセージを出して終了。**どの工程でチェックするか** は失敗の blast radius (下流再生成コスト) で決める。詳細は §12。
3. **3 レイヤ分離**:
   - 視覚レイヤ (`scenes.json`) — shot/composition/character placement、画中文字 (in_image_text)、吹き出し safe zone
   - テキスト・音響レイヤ (`bubbles.json`) — dialogue 吹き出し / SFX 音 / BGM cues
   - 演出レイヤ (`mix.json`) — 各 cue の timing と volume
   これを混ぜると後で 1 箇所いじっただけで全パネル再生成になる。
4. **4 キャラ/パネル制約**: nanobanana の reference image budget (stylesheet × 人数 + 直前パネル) を考えると **5人ではなく4人** が安全。シナリオ生成時に LLM に強制。
5. **Identity locking 必須**: 全パネル生成で各キャラの **stylesheet (turnaround + expressions) を必ず ref に添付**する。これをサボると数枚で別人になる。
6. **テキストはハイブリッド**: 種別で描く層を分ける。
   - **セリフ・モノローグ・ナレーション** = nanobanana に描かせない (negative: `text, speech bubbles, dialogue captions`) → **Pillow で後乗せ**。長文の正確性・再編集性・多言語化のため。
   - **擬音語 (SFX onomatopoeia)** と **環境テキスト** (看板・本のタイトル等) = **nanobanana に integrated に描かせる**。マンガの絵的要素なので統合された方が自然。1〜4文字のカタカナなら精度が出る。
   - これに伴い nanobanana プロンプトには `INTEGRATED TEXT:` (描かせる) と `NEGATIVE SPACE:` (吹き出し用に空けさせる) を明示する。
7. **吹き出し位置は画像を見て決める**: bubbles.json を書く LLM は **生成済みパネル画像を見て** `x_pct/y_pct` を決定する (S9 は S11 の後で実行)。`claude -p` でも `@path/to/panel.png` 参照で画像 Read 経由の vision 入力ができる。
8. **音声は3トラック**: voice / SFX / BGM を別トラックで保持し、最終段で ducking 付き mix。

---

## 2. ディレクトリ構成

```
webtoon-gen/
├── projects/
│   ├── _template/              # 新規小説のひな型
│   └── <novel_id>/
│       ├── project.yaml        # title / era / style / chapter markers / output targets
│       ├── characters.yaml     # 登場人物 (LLM自動生成 → 人がレビュー)
│       ├── lexicon.yaml        # 漢字読み補正辞書 (人名・地名)
│       ├── input/novel.txt     # UTF-8 全文
│       ├── characters/<id>/    # candidates/, selected.png, stylesheet_*.png
│       ├── work/chapters/<ch>/
│       │   ├── novel.txt           # 章テキスト
│       │   ├── scenes.json         # 視覚レイヤ
│       │   ├── bubbles.json        # テキスト+SFX+BGM レイヤ
│       │   ├── mix.json            # タイミング+音量レイヤ
│       │   ├── reviews/            # codex レビュー履歴
│       │   ├── panels/<scene>/<pid>_best.png
│       │   ├── bubbled/<scene>/<pid>_bubbled.png
│       │   ├── audio/voice/<pid>.wav      # Aivis
│       │   ├── audio/sfx/<pid>_<n>.wav    # ElevenLabs
│       │   ├── audio/bgm/<scene>.wav      # ElevenLabs ambience
│       │   ├── audio/mix/<pid>.wav        # 3-track 合成済み
│       │   ├── pages/<pid>.png
│       │   └── video_segs/
│       └── output/<ch>/
│           ├── webtoon.png
│           ├── webtoon_scroll.mp4
│           └── subtitles.srt
├── prompts/
│   ├── extract_characters.md
│   ├── decompose_scenes.md
│   ├── author_bubbles.md
│   └── review_scenario.md       # codex review 用
├── src/
│   ├── pipeline.py              # オーケストレータ
│   ├── project.py / llm.py
│   ├── novel_loader.py
│   ├── character_designer.py / style_sheet.py
│   ├── render_panels.py
│   ├── bubble_renderer.py / compose_webtoon.py
│   ├── narrate_aivis.py         # Aivis client
│   ├── synth_sfx.py             # ElevenLabs client
│   ├── synth_bgm.py             # ElevenLabs ambience client
│   ├── audio_mixer.py           # 3-track ducking mix
│   ├── scroll_video.py
│   └── subtitle.py              # SRT 生成
└── assets/fonts/                # ヒラギノ明朝/源暎アンチック等
```

---

## 3. パイプライン全体像

```
                   ┌─ project.yaml + input/novel.txt
                   ▼
[A] Setup ────────► characters.yaml + lexicon.yaml + voice assignments
                   ▼
[B] Visual ID ───► characters/<id>/{candidates,selected.png,stylesheet_*.png}
                   ▼
[C1] Scenes ─────► chapter/scenes.json (incl. in_image_text + safe_zones)
                   ▼ Codex review
[D1] Panels ─────► panels/*_best.png (画中文字込み, 吹き出し用 safe zone 確保)
                   ▼
[C2] Bubbles ────► chapter/bubbles.json — Claude が panels を見て位置決定
                   ▼ Codex review
[D2] Audio ──────► audio/{voice,sfx,bgm}/*.wav (Aivis + ElevenLabs)
                   ▼
[E] Compose ────► bubbled/*.png + audio/mix/*.wav + webtoon.png
                   ▼
[F] Video   ────► webtoon_scroll.mp4 + subtitles.srt
                   ▼
[G] Output  ────► YouTube 16:9 / TikTok 9:16 / 縦長 PNG (webtoon配信)
```

---

## 4. ステージ詳細

各ステージは `src/pipeline.py` から idempotent に呼ばれる。**[CHK]** = 人間レビュー停止点、**[LLM]** = Claude Code 起動、**[REVIEW]** = Codex 起動。

### A. Setup

#### S0. validate
- `project.yaml` 存在 / `input/novel.txt` 非空 / `.env` (GEMINI/ELEVENLABS/AIVIS) 確認
- Aivis サーバ (`http://127.0.0.1:10101/health`) 到達確認

#### S1. preprocess novel
- 入力が Aozora HTML なら ruby/annotation 除去 → UTF-8 plain
- `chapters[]` の `start_marker`/`end_marker` で `work/chapters/<ch>/novel.txt` に分割

#### S2. extract characters [LLM] [CHK]
- Claude が novel.txt から登場人物を抽出 → `characters.yaml`
- 各キャラに `description_en` (見た目) / `outfit_en` / `voice_model` (Aivis モデル候補名) を生成
- **「絵を作るキャラ (`expressions:` 有り)」と「説明のみキャラ」の区別** をLLMに判定させる
- → **[CHK]** 人がレビュー (固有名詞のtypo・voice_modelが妥当か等)

#### S3. lexicon [LLM] [CHK]
- Claude が novel.txt から固有名詞 (人名・地名・特殊語彙) を抽出
- 各語に推定読み (ひらがな) を付ける → `lexicon.yaml`
- → **[CHK]** 人がレビュー (「葉蔵=ようぞう」を確認、誤読を訂正)
- 後で TTS が読み上げる前にこの辞書で text を置換する

#### S4. assign voices
- `characters.yaml` の各キャラに対して Aivis Hub から model をダウンロード
  - `GET https://hub.aivis-project.com/api/v1/models?query=<voice_name>` で検索
  - `.aivmx` を取得 → `POST http://127.0.0.1:10101/aivm_models/install` でAivisに登録
  - 取得した `model_uuid` を `characters.yaml` に書き戻す
- → 自動 (失敗したら CHK)

### B. Visual identity

#### S5. character candidates
- 各「絵を作るキャラ」に対し、nanobanana で **4枚の候補** を seed違いで生成
- 候補は `characters/<id>/candidates/candidate_{1..4}.png` (3:4)

#### S6. select [CHK]
- HTMLグリッドビューワを開いて4枚を表示
- 人が選択 → `characters.yaml` に `selected_candidate: <N>` を記入
- → スクリプトが `cp candidates/candidate_<N>.png selected.png`

#### S7. stylesheets
- 各選択済みキャラに対し:
  1. **turnaround** — 4方向 (front / 3/4 / side / back) 全身フルボディシート (16:9)
  2. **expression** — 6表情の頭部グリッド (3:2)
  - **生成時に selected.png を ref として添付** (これがないと別人になる)
- 出力: `characters/<id>/stylesheet_{turnaround,expressions}.png`
- **重要**: スタイルシートは一度作ったら原則再生成しない (Gemini 非決定性で全パネルとidentityがdriftするため)

### C. Scenario authoring

#### S8. decompose scenes [LLM] [CHK]
- 入力: chapter novel.txt + characters.yaml + project.yaml
- Claude が **scenes.json** を生成:
  ```jsonc
  {
    "scenes": [
      {
        "id": "scene_01",
        "setting": {"location": "...", "time_of_day": "夕方", "era": "..."},
        "panels": [
          {
            "panel_id": "scene_01_p01",
            "shot_type": "wide_establishing",
            "camera_angle": "eye_level",
            "composition": "rule_of_thirds",
            "eye_line": "off_camera_left",
            "emotion_primary": "...",
            "emotion_secondary": "...",
            "lighting": "...",
            "background_style": "...",
            "aspect_ratio": "4:5",
            "treatment": "normal | symbolic_dark | imagined_surreal | photograph",
            "characters_in_panel": [
              {"id": "yozo_child", "pose": "sitting_seiza", "direction": "facing_camera"}
            ],
            "distance_to_next_panel": "tight | breath | jump",

            // 画中に nanobanana が描く文字 (擬音語・環境テキスト)。
            // セリフ・モノローグはここに入れない (それらは bubbles.json で PIL 後乗せ)。
            "in_image_text": [
              {
                "kind": "sfx",          // sfx (擬音語) | diegetic (看板・本タイトル等)
                "text": "ガタッ",        // 1〜4 文字のカタカナ推奨。長文不可
                "style_hint": "bold black katakana, manga onomatopoeia, motion-line aesthetic",
                "position": "upper-right",  // upper-left/upper-right/lower-left/lower-right/center
                "linked_sfx_id": "sfx_01"   // bubbles.json の panel.sfx[].id と紐付け (任意)
              }
            ],

            // 吹き出しを後乗せするために nanobanana に空けさせたい領域 (顔や detail を入れない)。
            // S9 で bubbles を配置する LLM がここを参考に x_pct/y_pct を決める。
            "bubble_safe_zones": [
              {"x_pct": 70, "y_pct": 5, "w_pct": 28, "h_pct": 35, "purpose": "narration_box"}
            ]
          }
        ]
      }
    ]
  }
  ```
- 制約 (LLMに明示):
  - **1パネル4キャラ以下** (5人以上のシーンはパネル分割で表現)
  - 1シーン3〜5パネル、1章6〜10シーン
  - 各シーンの最終パネルは `distance_to_next_panel: "jump"`
  - extreme_close_up_eyes は1章で1〜2回まで
  - `in_image_text[].text` は **1〜4文字** (5文字以上は崩れる)。長い擬音語は短縮 ("ザワザワザワ…" → "ザワザワ")
  - `in_image_text[].kind: sfx` を入れたパネルは bubbles.json の `panel.sfx[]` にも対応する音響エントリを置く (visual と audio をペアで)
  - `bubble_safe_zones[]` は吹き出し予定数+1 程度を最低確保 (狭すぎると後で詰まる)
- → **[CHK]** 人がざっと確認

#### S9. author bubbles [LLM-vision] [CHK]
**重要**: このステージは S11 (パネル画像生成) の **後** で実行する。bubbles の `x_pct/y_pct` を決めるには生成済みのパネル画像を見る必要があるため。

- 入力:
  - `scenes.json` (in_image_text と bubble_safe_zones が確定済み)
  - `chapter novel.txt`
  - **生成済みパネル画像** `panels/<scene_id>/<pid>_best.png` (S11 完了後)
  - `lexicon.yaml`
- Claude を vision モードで起動 (`claude -p` でも prompt body に `@<panel_path>.png` を含めれば Read tool 経由で画像を見る)
- Claude が画像を見て **bubbles.json** を生成:
  ```jsonc
  {
    "panels": [
      {
        "panel_id": "scene_01_p01",
        "bubbles": [
          {
            "type": "narration_box | monologue_box | speech | thought",
            "speaker": "narrator | yozo_child | ...",
            "text": "ああ、そうか、...",
            "reading_override": "ああ、そうか、...",  // optional, lexicon反映済み
            "x_pct": 70, "y_pct": 8, "width_pct": 26, // panel画像を見て決定 (safe zone内推奨)
            "tail_target": {"x_pct": 40, "y_pct": 60}, // null for narration_box
            "font_size_pt": 14,
            "vertical_text": true,
            "anchor_safe_zone_idx": 0   // scenes.json の bubble_safe_zones[N] と紐付け (検証用)
          }
        ],
        "sfx": [
          // 音響としての SFX (ElevenLabs で wav 生成 → 動画にミックス)。
          // 同じ panel の scenes.json.in_image_text[].linked_sfx_id と id 一致で
          // 「絵に描かれた擬音語」と「鳴る音」がペアになる。
          {
            "id": "sfx_01",
            "start_offset_s": 0.0,
            "duration_s": 1.5,
            "elevenlabs_prompt": "soft footsteps on wooden floorboards, traditional Japanese house",
            "volume_db": -8
          }
        ],
        "bgm_cue": null   // null | "fade_out" | "fade_in:<scene_id>"
      }
    ],
    "scene_bgm": [
      {
        "scene_id": "scene_01",
        "elevenlabs_prompt": "quiet melancholic ambient drone, distant cicadas, evening",
        "volume_db": -18,
        "loop": true
      }
    ]
  }
  ```
- 制約:
  - **顔・焦点を吹き出しで隠さない** — Claude がパネル画像を見て、顔の bounding box を避ける
  - **safe zone 優先** — `scenes.json.bubble_safe_zones[]` 内に収めるのを第一候補。やむを得ず外す場合 `notes` 欄に理由
  - 縦書き読み順は右上→左下
  - SFX は ElevenLabs Sound Effects 制約 (1呼び出し ≤22秒)
  - BGM は scene 単位、ループ前提のambience
  - SFX の `id` は `scenes.json.in_image_text[].linked_sfx_id` と一致させる (絵と音をペアに)
- フォールバック (vision LLMが効かない場合):
  - `bubble_safe_zones[0]` の中央を初期位置にして書き、後で人が直す
  - もしくは `mediapipe` で顔検出 → 顔と被ってる bubble を最寄りの安全領域に自動退避
- → **[CHK]** 人がパネル画像と bubbles.json を並べて確認 (位置・読み・SFX妥当性)

#### S10. review [REVIEW] [CHK]
- Codex に scenes.json + bubbles.json + novel.txt を渡してレビュー
- Codex は `reviews/<chapter>/round_<N>.md` に**構造化フィードバック**を書く:
  ```markdown
  ## Severity: blocker
  - [scene_02_p03] 5人映っているが nanobanana 制約に違反
  - [scene_05] BGM が前後で繋がっていない (scene_04 fade_out が無い)

  ## Severity: major
  - [scene_03_p01] モノローグが原作と乖離 ("私は..." → 原作 "自分は...")

  ## Severity: minor
  - [scene_07_p02] eye_line が前パネルと180度ライン跨ぎ
  ```
- Claude にこの md を読ませて scenes.json/bubbles.json を修正 → 再度Codexレビュー
- 終了条件: blocker=0 かつ major≤2、または手動 approve
- 最大 3 ラウンド。それでも収束しなければ手動介入

### D. Asset generation

#### S11. render panels (image)
**重要**: S9 (bubbles) は S11 の出力を必要とするため、S11 → S9 の順で走る。

- scenes.json の各 panel について nanobanana で生成
  - prompt 構築: shot/composition/character ID → description_en + outfit_en (project の era + style 注入)
  - **必ず添付する ref**:
    - 各キャラの stylesheet_turnaround.png + stylesheet_expressions.png + selected.png
    - 直前パネルの `_best.png` (連続性)
  - **画中文字 (`in_image_text[]`) を positive 指定** で勧誘:
    ```
    INTEGRATED TEXT (drawn as part of the artwork — NOT in a speech bubble):
    - a manga sound effect "ガタッ" rendered in bold black katakana with motion-line aesthetic, placed in the upper-right of the frame
    - a vertical wooden signboard reading "東京駅", weathered and aged
    ```
  - **`bubble_safe_zones[]` を negative space 指示** で確保:
    ```
    NEGATIVE SPACE — leave these regions visually quiet (no faces, no fine detail, light/empty background) so a speech bubble can be overlaid later:
    - upper-right region around x=70%, y=5%, w=28%, h=35%
    ```
  - negative: `speech bubbles, dialogue captions, watermark, modern clothing, color` (project monochrome の場合)
    - **注意**: `text` を一括禁止すると in_image_text まで消えるので NG。`speech bubbles` と `dialogue captions` のみ禁止する
  - aspect: panel.aspect_ratio
- 出力: `panels/<scene_id>/<pid>_best.png`
- `reuse_from` 指定があるパネルは生成スキップで参照先パスを使う
- **2pass 戦略 (オプション)**: 1pass目で in_image_text 抜きで描画 → S9 で位置決定 → 2pass目で in_image_text と詳細 safe zone を追加して再生成。コスト2倍だが品質は上がる。デフォルトは 1pass

#### S12. quality review (per panel) [optional but recommended]
- 各パネルを VLM (Claude or Codex) に渡して採点
  - rubric: identity一致 / shot準拠 / 視線 / 表情 / 連続性 / 時代考証 / 致命欠陥(指/顔)
- 閾値以下 or 致命欠陥フラグ → プロンプト摂動して再生成
- 最大 3 ラウンド/パネル

#### S13. synthesize voice (Aivis) [3層の読み制御]

各 bubble について **3 層** で読みを制御する。1 層目で大半、2 層目で詰め、3 層目で取りこぼしを検出。

**層 1: lexicon 前置換**
```python
# text: "葉蔵は道化を演じた"
text = apply_lexicon(bubble.text, lexicon.yaml)
# → "ヨウゾウはどうけをえんじた"   (人名・特殊語彙のみカタカナ化)
```

**層 2: audio_query エディット (VOICEVOX 互換 API)**

`/v1/audio/speech` (OpenAI 互換) ではなく **`/audio_query` + `/synthesis`** を使うと読みを編集できる:

```python
# 1. text → AudioQuery (予測読み入り)
aq = POST /audio_query?text={text}&speaker={style_id}
# aq.accent_phrases[].moras[].text に予測カタカナが入っている

# 2. 既知語の読みを検証・上書き
for word in lexicon.words:
    expected_moras = kana_to_moras(word.reading)
    found_idx = find_phrase_for_surface(aq, word.surface)
    if found_idx is not None:
        aq.accent_phrases[found_idx].moras = expected_moras

# 3. 速度・抑揚を character/bubble 指定で調整
aq.speedScale = character.voice_speed
aq.pitchScale = bubble.get("pitch_scale", 0.0)

# 4. 合成
wav = POST /synthesis?speaker={style_id}  body=aq
```

**層 3: Whisper 後検証ループ**

```python
transcript = whisper.transcribe(wav, lang="ja")
sim = hira_similarity(bubble.text, transcript)   # 両方ひらがな化して Levenshtein
if sim < 0.88:
    diff = find_mismatch_position(bubble.text, transcript)
    log_to(work/chapters/<ch>/voice_review.md, {
        "panel_id": pid,
        "bubble_idx": i,
        "intended": bubble.text,
        "transcript": transcript,
        "similarity": sim,
        "suggested_lexicon_entry": {"surface": diff.kanji, "reading": diff.expected_kana}
    })
    # 自動修正は人レビュー後 (S13b)
```

#### 実装

- **長文 bubble は narrate 側で自動分割** (`src/subtitle_split.py`)
  - bubbles.json に書かれた text が 35 文字 (日本語全角 1 行分) を超えると
    自然な区切り (句点 → 読点 → ハード分割) で複数 chunk に分け、それぞれ
    別の Aivis 呼び出し + 別字幕として扱う
  - bubbles.json 自体はオリジナルのまま (人手で書いた長文を保護)
  - 1 字幕が常に 1 行に収まるので、字幕焼き込み時にレイアウト崩れなし
- bubble ごとに wav 生成 → ffmpeg concat で 1 パネル 1 ファイル化
- 話者違いの bubble は **speaker を切り替えて別合成 → 連結** (mix ではない)
- セリフが無いパネルは **1.2 秒の無音 wav** (動画ホールド時間確保)
- Whisper モデル:
  - macOS デフォルト: `whisper.cpp` + large-v3-turbo (Metal 加速)
  - フォールバック: OpenAI API (`/v1/audio/transcriptions`)
  - `project.yaml` の `voice.verify: true|false` で ON/OFF (デフォルト ON)
  - 閾値 `voice.similarity_threshold: 0.88`
- 出力:
  - `audio/voice/<pid>.wav`
  - `voice_review.md` に検証失敗エントリ (人がレビューして lexicon.yaml にマージ)

#### S13b. lexicon 補強 [CHK]

S13 の `voice_review.md` に検出された誤読候補を人が確認 → lexicon.yaml に追加 → 該当パネルだけ `--force-bubble <pid>` で再合成。

```bash
# 検証で 5 件の誤読が検出された場合
$EDITOR projects/<id>/lexicon.yaml          # 候補を採否判定してマージ
uv run python -m src.pipeline <id> --resynth-failed-voices
```

---

#### S14. synthesize SFX (ElevenLabs)
- bubbles.json の各 panel.sfx[] エントリについて
  - `POST https://api.elevenlabs.io/v1/sound-generation`
    ```json
    {"text": "<elevenlabs_prompt>", "duration_seconds": <duration_s>, "prompt_influence": 0.7}
    ```
  - 出力 mp3 を `audio/sfx/<pid>_<n>.mp3` に保存

#### S15. synthesize BGM (ElevenLabs ambience)
- bubbles.json の `scene_bgm[]` 各エントリについて
  - SFX API は最長 ~22秒。**シーン全長 (=シーン内全パネルの voice 長 + 間 の合計) を見積もって**、その長さに足りる ambience を生成し、ffmpeg で **`-stream_loop` ループ + 両端 fade** を掛ける
  - 出力: `audio/bgm/<scene_id>.wav`

### E. Composition

#### S16. render bubbles (PIL)
- 各 panel image に対して bubbles.json の bubbles[] を Pillow で後乗せ
  - 縦書き日本語 (font: ヒラギノ明朝 or 源暎アンチック)
  - 吹き出しタイプ別の形状: speech=楕円+尻尾, thought=雲, narration_box=角丸矩形, monologue_box=矩形
  - 顔検出は使わず、bubbles.json の `x_pct/y_pct` を信頼 (位置は S9 で決定済み)
- 出力: `bubbled/<scene_id>/<pid>_bubbled.png`

#### S17. compose webtoon PNG
- 全パネル (bubbled or 素のpanel) を幅 800px に揃えて縦結合
- `distance_to_next_panel` を参照して間隔調整 (tight=20, breath=80, jump=200)
- 同時に `panel_positions.json` を出力 (各パネルの y_start/y_end → 動画化で使う)
- 出力: `output/<chapter>/webtoon.png`

#### S18. mix audio (3-track per panel)
- 各パネルについて voice + 同一パネルの SFX[] + 該当 scene の BGM を ffmpeg で mix
- ducking recipe (voice 主役):
  ```bash
  ffmpeg -i voice.wav -i sfx_1.wav -i sfx_2.wav -i bgm.wav \
    -filter_complex "
      [1:a]adelay=500|500[s1];
      [2:a]adelay=2000|2000[s2];
      [s1][s2]amix=inputs=2:normalize=0[sfx];
      [3:a]volume=-18dB[bgmlow];
      [bgmlow][0:a]sidechaincompress=threshold=0.05:ratio=8:attack=5:release=200[bgmducked];
      [0:a][sfx][bgmducked]amix=inputs=3:normalize=0:weights='1.5 0.8 0.6'[out]
    " -map "[out]" -ar 44100 -c:a pcm_s16le mix.wav
  ```
  - voice は等倍 (weight 1.5)
  - SFX は voice にぶつからないよう adelay でタイミング指定
  - BGM は -18dB から sidechain で voice 中だけさらに圧縮 (=ducking)
- 出力: `audio/mix/<pid>.wav`

#### S19. generate subtitles (SRT)
- bubbles.json と各 voice wav の duration から SRT を組み立てる
  - 開始時刻 = 各パネルの累積開始時刻
  - 終了時刻 = 開始 + voice duration
  - text = bubble.text (narration_box/speech 区別なくフラット)
- 出力: `output/<chapter>/subtitles.srt`

### F. Video assembly

#### S20. build pages
- `webtoon.png` を幅1080pxに rescale
- 各パネルを 1080×1920 frame に中央配置 (パネル外は near-black)
- 出力: `pages/<pid>.png`

#### S21. build hold-then-scroll segments
- 各パネルについて:
  1. **hold clip** = ページ画像 + `audio/mix/<pid>.wav` (固定、duration=audio長)
  2. **transition clip** = 前ページから次ページへ垂直スクロール (0.5s, silent)
- ffmpeg で連結 → `output/<chapter>/webtoon_scroll.mp4`

### G. Output formats

#### S22. encode per target
- **YouTube 横長**: 1080×1920 → 1920×1080 letterbox (上下に黒帯) or pad
- **TikTok / Reels**: 1080×1920 そのまま、長さ60s以下にカット (シーン単位で切る)
- **Webtoon配信 (LINE/comico等)**: 動画ではなく `output/<chapter>/webtoon.png` 単体を提出

---

## 5. データスキーマ集約

### project.yaml
```yaml
id: <novel_id>
title_ja: ...
language: ja
era: "early Showa era Japan, 1920s-1930s"
locale_hint: "rural Tohoku and Tokyo"
style:
  description: "monochrome black-and-white webtoon manga, ..."
  negative: "text, speech bubbles, color, ..."
chapters:
  - id: chapter_01
    start_marker: 第一の手記
    end_marker: 第二の手記
narrator:
  voice_model_uuid: "<aivis uuid>"
  default_speed: 1.0
voice:
  engine: aivis              # aivis | openai (将来別 TTS 追加時用)
  endpoint: "http://127.0.0.1:10101"
  verify: true               # Whisper 後検証を行うか
  similarity_threshold: 0.88 # ひらがな化後 Levenshtein で 0.88 未満で不一致扱い
  whisper:
    backend: whisper_cpp     # whisper_cpp | openai_api
    model: large-v3-turbo
bubbles:
  font_path: "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc"
  font_index: 0
  font_scale: 1.5
webtoon:
  width_px: 800
  panel_gap_px: { tight: 20, breath: 80, jump: 200 }
video:
  canvas_w: 1080
  canvas_h: 1920
  fps: 30
  transition_s: 0.5
output_targets:   # S22 で使う
  - { name: youtube_shorts, aspect: "9:16", max_duration_s: 60 }
  - { name: webtoon_png_only, kind: "static" }
review:
  reviewer: codex
  max_rounds: 3
```

### characters.yaml
```yaml
characters:
  - id: yozo_child
    name_ja: 大庭葉蔵（幼少）
    description_en: "..."
    outfit_en: "..."
    expressions: ["neutral", "performative_smile", "hollow_stare", ...]    # 有り = 絵を作る
    poses: ["front", "three_quarter", "side_profile", "back"]
    selected_candidate: 2
    voice_model_uuid: "abc123-..."
    voice_speed: 1.0
    voice_intensity: 0.7
  - id: father
    description_en: "..."
    expressions: []          # 空 = 説明のみ
    voice_model_uuid: "def456-..."
```

### lexicon.yaml
```yaml
words:
  - { surface: 葉蔵, reading: ようぞう, kind: name }
  - { surface: 大庭, reading: おおば, kind: name }
  - { surface: 円タク, reading: えんたく, kind: noun }
  - { surface: 銘仙, reading: めいせん, kind: noun }
```

### scenes.json (S8 出力 — 視覚レイヤ)
```jsonc
{
  "scenes": [
    {
      "id": "scene_01",
      "title": "夕方の縁側",
      "setting": {"location": "葉蔵の家・縁側", "time_of_day": "夕方", "era": "early Showa Japan"},
      "panels": [
        {
          "panel_id": "scene_01_p01",
          "shot_type": "wide_establishing",
          "camera_angle": "eye_level",
          "composition": "rule_of_thirds",
          "eye_line": "off_camera_left",
          "emotion_primary": "quiet_resignation",
          "emotion_secondary": "hollow_dread",
          "lighting": "soft_window_light_from_right",
          "background_style": "engawa_blurred",
          "aspect_ratio": "4:5",
          "treatment": "normal",
          "characters_in_panel": [
            {"id": "yozo_child", "pose": "sitting_seiza", "direction": "facing_camera"}
          ],
          "distance_to_next_panel": "breath",

          // 画中に nanobanana が描く文字 (擬音語・看板等)。
          // セリフ・モノローグはここに入れない。1〜4 文字推奨。
          "in_image_text": [
            {
              "kind": "sfx",
              "text": "ザワザワ",
              "style_hint": "soft black katakana, manga atmosphere onomatopoeia",
              "position": "background-right",
              "linked_sfx_id": "sfx_01"
            }
          ],

          // 後で吹き出しを乗せる用に nanobanana に「絵を入れない」と指示する領域
          "bubble_safe_zones": [
            {"x_pct": 70, "y_pct": 5, "w_pct": 28, "h_pct": 35, "purpose": "narration_box"}
          ],

          "intent": "夕方の縁側を確立、葉蔵の道化の下の虚無を匂わせる",
          "reuse_from": null
        }
      ]
    }
  ]
}
```

### bubbles.json (S9 出力 — テキスト・音響レイヤ)
S9 は **生成済みパネル画像を見て** Claude が書く (S11 の後)。

```jsonc
{
  "panels": [
    {
      "panel_id": "scene_01_p01",
      "bubbles": [
        // PIL で後乗せされる吹き出しテキスト。長文 OK。
        {
          "type": "narration_box",        // narration_box | monologue_box | speech | thought
          "speaker": "narrator",          // narrator | <character_id>
          "text": "恥の多い生涯を送って来ました。",
          "reading_override": null,       // optional, lexicon を上書きしたい時
          "x_pct": 70, "y_pct": 8,        // 画像を見て決定 (safe zone 内推奨)
          "width_pct": 26,
          "tail_target": null,            // null for narration/monologue boxes
          "font_size_pt": 14,
          "vertical_text": true,
          "anchor_safe_zone_idx": 0,      // scenes.json の bubble_safe_zones[N] と紐付け (検証用)
          "notes": null                   // safe zone外に置いた理由など
        }
      ],
      "sfx": [
        // 音響としての SFX (ElevenLabs で wav 生成 → 動画にミックス)。
        // scenes.json の同パネル in_image_text[].linked_sfx_id と id 一致でペアになる。
        {
          "id": "sfx_01",
          "start_offset_s": 0.0,
          "duration_s": 2.5,
          "elevenlabs_prompt": "distant cicadas at dusk, quiet residential atmosphere",
          "volume_db": -12
        }
      ],
      "bgm_cue": null   // null | "fade_out" | "fade_in:<scene_id>" — 場面転換でBGMをコントロール
    }
  ],
  "scene_bgm": [
    {
      "scene_id": "scene_01",
      "elevenlabs_prompt": "quiet melancholic ambient drone, distant cicadas, evening",
      "volume_db": -18,
      "loop": true
    }
  ],
  "font_main": "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc",
  "font_index": 0,
  "font_scale": 1.5
}
```

### mix.json (S18 入力 — タイミング+音量、bubbles.json から派生)
通常は bubbles.json から自動生成され直接編集しない (各 voice wav の duration を ffprobe で確定、SFX の start_offset を反映)。

```jsonc
{
  "panels": [
    {
      "panel_id": "scene_01_p01",
      "voice_path": "audio/voice/scene_01_p01.wav",
      "voice_duration_s": 4.32,
      "sfx_tracks": [
        {"path": "audio/sfx/scene_01_p01_01.mp3", "start_s": 0.0, "duration_s": 2.5, "volume_db": -12}
      ],
      "bgm_path": "audio/bgm/scene_01.wav",
      "bgm_volume_db": -18,
      "ducking": {"threshold": 0.05, "ratio": 8, "attack_ms": 5, "release_ms": 200}
    }
  ]
}
```

---

## 6. 主要 ffmpeg レシピ

### BGM ループ＋両端フェード
```bash
ffmpeg -stream_loop -1 -i ambience.mp3 -t <scene_total_s> \
  -af "afade=t=in:d=0.8,afade=t=out:st=$((scene_total_s-1)):d=1.0" \
  audio/bgm/<scene>.wav
```

### 3-track ducking mix
S18 のコマンド参照。

### hold clip
```bash
ffmpeg -loop 1 -t <dur> -i page.png -i audio_mix.wav \
  -map 0:v -map 1:a -c:v libx264 -tune stillimage -crf 20 \
  -c:a aac -b:a 192k -pix_fmt yuv420p hold.mp4
```

### transition (vertical scroll)
1080×3840 のスタック画像に対して:
```bash
ffmpeg -loop 1 -t 0.5 -i stacked.png -f lavfi -t 0.5 -i anullsrc \
  -filter_complex "[0:v]crop=1080:1920:0:'1920*t/0.5',fps=30,format=yuv420p[v]" \
  -map "[v]" -map 1:a -c:v libx264 -c:a aac trans.mp4
```

---

## 7. Codex レビュー プロトコル

### 入力 (Codex CLI に渡す)
```bash
codex review \
  --novel projects/<id>/work/chapters/<ch>/novel.txt \
  --scenes projects/<id>/work/chapters/<ch>/scenes.json \
  --bubbles projects/<id>/work/chapters/<ch>/bubbles.json \
  --project projects/<id>/project.yaml \
  --characters projects/<id>/characters.yaml \
  --output projects/<id>/work/chapters/<ch>/reviews/round_<N>.md
```

### 観点リスト (review_scenario.md)
- **原作整合性**: 重要セリフの過不足、モノローグの語彙、人名表記
- **視覚制約**: 1パネル≤4キャラ、180度ライン、eye-line continuity、距離感の流れ
- **テクスチャ**: 吹き出しが顔/焦点を隠していないか、読み順が右上→左下
- **画中文字 (in_image_text)**:
  - sfx は1〜4文字カタカナか
  - 擬音語が原作の音にマッチしているか (捏造していないか)
  - in_image_text と bubbles.sfx が `linked_sfx_id` で対応しているか (絵と音のペア)
- **safe_zones**: bubbles の数に対して safe zone が足りているか、矩形が小さすぎないか
- **音響**: BGM が scene 間で繋がっているか、SFX が原作にない物を捏造していないか
- **ペース**: モノローグ比率、jump (場面転換) の頻度

### 出力フォーマット
```markdown
# review round 1 — <chapter_id>

## blocker (must-fix)
- panel_id / scene_id: 問題 / 修正案

## major (should-fix)
- ...

## minor (nice-to-fix)
- ...

## approved
- 良かったところ (Claude が次回参考にできるよう)
```

### Claude 側の処理
- 各 round_N.md を読み、blocker と major に対して scenes.json/bubbles.json をパッチ
- パッチ後を round_<N+1>.md で再レビュー
- 終了条件: blocker=0 ∧ major≤2 ∨ round=3

---

## 8. オーケストレータ pipeline.py のステージマップ

実行順序に注意: **S11 (panel生成) は S9 (bubbles 配置) の前**。bubbles の x_pct/y_pct を画像見て決めるため。

| 実行順 | Stage | LLM | 自動 | CHK | 出力 |
|---|---|---|---|---|---|
| 1 | S0 validate | | ● | | - |
| 2 | S1 split novel | | ● | | chapters/<ch>/novel.txt |
| 3 | S2 extract characters | ● | | ● | characters.yaml |
| 4 | S3 lexicon | ● | | ● | lexicon.yaml |
| 5 | S4 install voices | | ● | | (Aivis registered) |
| 6 | S5 character candidates | | ● | | candidates/*.png |
| 7 | S6 select | | | ● | selected.png |
| 8 | S7 stylesheets | | ● | | stylesheet_*.png |
| 9 | S8 scenes (incl. in_image_text + safe_zones) | ● | | ● | scenes.json |
| 10 | S10a codex review (scenes) | (●) | | ● | reviews/round_<N>_scenes.md |
| 11 | **S11 render panels** | | ● | | panels/*_best.png |
| 12 | S12 quality retry | (●) | ● | | (refinement) |
| 13 | **S9 bubbles (vision, sees panels)** | ● | | ● | bubbles.json |
| 14 | S10b codex review (bubbles) | (●) | | ● | reviews/round_<N>_bubbles.md |
| 15 | S13 voice (Aivis 3層: lexicon→audio_query→Whisper) | | ● | | audio/voice/*.wav + voice_review.md |
| 15.5 | S13b lexicon 補強 (Whisper 検出分) | | | ● | lexicon.yaml 追記 |
| 16 | S14 sfx (ElevenLabs) | | ● | | audio/sfx/*.mp3 |
| 17 | S15 bgm (ElevenLabs) | | ● | | audio/bgm/*.wav |
| 18 | S16 bubbles render (PIL) | | ● | | bubbled/*.png |
| 19 | S17 webtoon stitch | | ● | | output/<ch>/webtoon.png |
| 20 | S18 audio mix | | ● | | audio/mix/*.wav |
| 21 | S19 subtitles | | ● | | output/<ch>/subtitles.srt |
| 22 | S20 pages | | ● | | pages/*.png |
| 23 | S21 hold-then-scroll | | ● | | webtoon_scroll.mp4 |
| 24 | S22 per-target encode | | ● | | output/*/{shorts,reels,longform}.mp4 |

実行は `uv run python -m src.pipeline <novel_id> [--chapter <ch>] [--from <stage>] [--force]`。

---

## 9. 開発の進め方 (実装順)

ベスト構成を一気には作らない。動く最小単位 → 機能追加。

### M1: 既存 webtoon-gen の継続
既に動いている: S0/S1/S5-S8 (一部 LLM stub)/S11/S16/S17/S20/S21、TTSは OpenAI で代用。

### M2: TTS を Aivis に置き換え (基本)
- `src/narrate.py` (現 OpenAI) → `src/narrate_aivis.py`
- `/v1/audio/speech` でとりあえず動かす (層1の lexicon 前置換のみ)
- `characters.yaml` に `voice_model_uuid` 追加
- S4 (voice install) を新設

### M3: SFX/BGM 追加 + 画中文字 + S9 vision 化
- `src/synth_sfx.py` (ElevenLabs)
- `src/synth_bgm.py` + ループ加工
- scenes.json schema 拡張 (`in_image_text[]`, `bubble_safe_zones[]`)
- bubbles.json schema 拡張 (`sfx[]`, `scene_bgm[]`, `linked_sfx_id` 紐付け)
- `src/render_panels.py` の prompt 構築で `INTEGRATED TEXT:` と `NEGATIVE SPACE:` を追加
- `src/llm.py` に `author_bubbles(project, chapter)` を追加 (Claude にパネル PNG を `@path` で見せて bubbles.json を書かせる)
- pipeline の実行順を **S11 → S9** に変更 (S11 で panel 生成 → S9 で画像見て bubble 配置)
- S14/S15 を pipeline に追加

### M4: 3-track mix
- `src/audio_mixer.py` (ffmpeg sidechain)
- S18 を pipeline に追加、scroll_video が mix.wav を使う

### M5: Lexicon + 読み制御強化 (3層化)
- `lexicon.yaml` schema (S3 で Claude が初期生成)
- 層1: 各 TTS 呼び出し前に lexicon 前置換
- 層2: `/v1/audio/speech` から **`/audio_query` + `/synthesis`** へ切り替え。`accent_phrases[].moras[]` を検査して既知語の読みを上書き
- 層3: `src/voice_verify.py` を追加。whisper.cpp で生成 wav を文字起こし、`pykakasi` でひらがな化、`rapidfuzz` で類似度判定。閾値以下を `voice_review.md` に出す
- S13b (lexicon 補強チェックポイント) を pipeline に追加

### M6: Codex レビュー
- `prompts/review_scenario.md`
- `src/codex_review.py` (Codex CLI 呼び出し)
- S10 を pipeline に追加 (S8/S9 の後)

### M7: Quality retry on panels
- `src/critic.py` で VLM 採点
- S12 を pipeline に追加

### M8: 出力先別エンコード
- `src/encode_targets.py`
- `project.yaml.output_targets[]` ループ
- S22 を pipeline に追加

### M9: 人レビュー用 desktop アプリ
M1〜M8 で「Claude Code から指示して動く」状態が出来てから、人レビュー (§12 Tier 1〜3) を効率化する desktop アプリを追加。基本は Claude Code 主導のままで、レビュー・微調整・再生成だけアプリで楽にする。詳細は §13。

- M9a: read-only viewer (パネル + 音声 + 完成動画を一覧表示)
- M9b: 直接再生成 (Claude 不要: voice/bubble/SFX/BGM/mix の差し替え)
- M9c: コメント機能 + Claude タスクランナー
- M9d: 仕上げ (.app パッケージ化, 複数プロジェクト切替)

---

## 10. 落とし穴と対策

| 罠 | 対策 |
|---|---|
| nanobanana で5人以上書かせる→主人公が消える | scenes.json で4人制約をLLMに強制 |
| stylesheet 再生成で全パネルがdriftする | 一度作ったら archival 扱い、`--force` でも避ける |
| nanobanana がセリフ吹き出しを勝手に描く | negative に `speech bubbles, dialogue captions` (`text` 単独で禁止すると in_image_text まで消えるので NG) |
| 擬音語が PIL 後乗せだとマンガぽくない | `in_image_text[]` で nanobanana に integrated に描かせる。1〜4 文字カタカナに限定 |
| 吹き出しが顔に被る | scenes.json で bubble_safe_zones を確保 + S9 を vision LLM にして画像見て位置決定 + mediapipe フォールバック |
| nanobanana が長い日本語を化けさせる | 長文 (5文字以上) は scenes.json に入れず PIL で後乗せ。画中文字は1〜4文字に制限 |
| Aivis の reading が kanji を間違える | 3層で防御: ①lexicon.yaml 前置換 ②`/audio_query` の moras を検査して上書き ③Whisper で生成 wav を文字起こしして類似度 < 0.88 を検出 → voice_review.md に書き出して lexicon に追加 |
| Whisper も漢字を読み間違える | 比較は両方ひらがな化してから (pykakasi) Levenshtein。漢字レベル比較は偽陽性多発 |
| lexicon.yaml が育たない | S13 の voice_review.md にある未登録語を S13b で人がマージするフローを習慣化。1 章ごとに 5〜10 語増えるイメージ |
| BGMがvoiceにかぶる | sidechain ducking 必須 (ad-hoc -18dB だけだと不足) |
| ElevenLabs SFXが22秒以上欲しい | ループ＋fade で延長 |
| scenes.json が原作から逸脱 | Codex レビューで blocker 検出 |
| 候補4枚が全部似てる | seed強制、batch generation でなく個別呼び出し |
| 章の境界で BGM が途切れる | scene_bgm に fade_out / fade_in_next 指定 |
| スクロール動画でセリフを追えない | hold-then-scroll、連続スクロールにしない |
| 同一パネルで複数キャラのvoiceが混ざる | bubble 単位で別合成 → ffmpeg concat (mix ではない) |
| in_image_text と sfx の音/絵が一致しない | scenes.json.in_image_text[].linked_sfx_id と bubbles.json.panel.sfx[].id を必ず対応させる |
| safe_zone を狭く取りすぎてフォントが入らない | 1 zone あたり最低 w_pct 20% 以上、複数吹き出し見込むなら数を多めに |

---

## 11. 一発実行イメージ

```bash
# 新しい小説を追加
cp -r projects/_template projects/<novel_id>
mv projects/<novel_id>/project.yaml.example projects/<novel_id>/project.yaml
$EDITOR projects/<novel_id>/project.yaml         # title, era, chapters
cp /path/to/novel.txt projects/<novel_id>/input/novel.txt

# 走らせる (停止点まで一気に進む)
uv run python -m src.pipeline <novel_id>
# → S2で停止 ("characters.yaml をレビューして再実行してね")

$EDITOR projects/<novel_id>/characters.yaml
uv run python -m src.pipeline <novel_id>
# → S3で停止 ("lexicon.yaml をレビューして再実行")

$EDITOR projects/<novel_id>/lexicon.yaml
uv run python -m src.pipeline <novel_id>
# → S6で停止 ("候補画像を見て selected_candidate を入れて")

# … 以降S8/S9/S10レビュー往復 …

# 全章完成
ls projects/<novel_id>/output/*/webtoon_scroll.mp4
```

---

## 12. 人レビューポリシー (どこで人が見るか)

API 利用料・compute・人の時間は無限ではない。「どの工程で人が見ると ROI が高いか」を **失敗の blast radius (下流再生成コスト) × 検出のしやすさ** で決める。

### 大原則

ある工程の失敗が下流に波及する範囲が広い = その前のチェックの ROI が大きい。

```
S2 characters.yaml ──→ 候補・stylesheet・全パネルの土台 ($10〜30 損失)
S3 lexicon.yaml ─────→ 全 wav の読み (再合成 + 再 mix の手間)
S6 selected.png ─────→ 全パネルの主人公 ($2〜5/キャラ)
S7 stylesheet ───────→ 全パネルの identity ($5〜10、driftで全作り直し)
S8 scenes.json ──────→ シーン全パネル ($0.2〜0.4/scene)
S9 bubbles.json ─────→ PIL 再描画 (無料だが位置決めやり直し)
S12 panel quality ───→ 1 panel ($0.04)
S13b voice review ───→ 1 bubble (無料)
```

### Tier 1 — 必ず人がチェック (4 工程)

スキップすると下流で何倍ものコストを失う。代替できない領域。

| # | 工程 | 何を見るか | 所要 |
|---|---|---|---|
| ① | **S2 characters.yaml** | 主要キャラの抜け漏れ / `expressions:` の有無で「絵にする」「説明だけ」の分類 / 年齢別バリアントの分割 | 5 分 |
| ② | **S3 lexicon.yaml** | 主要人名・地名の読み / 漢字 → 意図しないひらがな化が無いか | 5〜10 分 |
| ③ | **S6 candidate selection** | 4 候補から 1 つ選ぶ (主観・自動化不可) | 30 秒/キャラ × N |
| ④ | **S7 stylesheet 視認** | turnaround 4 ポーズで顔・服が同じか / 6 表情で別人化していないか / 致命欠陥 | 30 秒/キャラ × N |

### Tier 2 — Codex 主、人が spot-check (3 工程)

LLM レビューで大半は捌ける。人は最終判断と粒度の合わない部分だけ見る。

| # | 工程 | Codex に任せる | 人が見る | 所要 |
|---|---|---|---|---|
| ⑤ | **S8 scenes.json** | 4キャラ違反検出、180度ライン、in_image_text 整合 | blocker の納得感、モノローグ密度の感覚 | 5 分 |
| ⑥ | **S9 bubbles.json** | 顔被り検出 (画像同梱)、読み順、linked_sfx_id | 重要パネルの bubbled プレビュー | 5 分 |
| ⑦ | **S13b voice_review.md** | Whisper 検証で類似度 < 0.88 の bubble + 推定読み候補を自動収集 | 提案された lexicon エントリの採否 → マージ → `--resynth-failed-voices` | 2〜3 分 |

### Tier 3 — 最終 QA (省略不可)

| # | 工程 | 何を見るか | 所要 |
|---|---|---|---|
| ⑧ | **完成動画 1 通し視聴** | BGM が章境で切れる/voice と SFX の被り/フォントサイズ/スクロール速度 | 動画長 (倍速可、5〜10 分) |

個別 stage が全部 OK でも合成後にしか分からない問題がここで出る。

### Tier 4 — 自動で十分 (人は見ない)

- **S0 validate / S1 split / S4 voice install** — 失敗ならエラーで止まる
- **S5 candidate generation** — 結果は S6 で人が見る
- **S11 panel rendering** — S12 自動 retry で十分
- **S12 panel quality** — VLM critic + 自動 retry max 3。3 ラウンド失敗したパネルだけ Tier 1 扱いに昇格 (人レビュー)
- **S14/S15 SFX/BGM 生成** — 単体は最終 QA でまとめて聴く
- **S16-S22 合成・動画化** — 決定的処理

### Pipeline 内のチェック挿入位置

```
[A] Setup
    S0/S1 (auto)
    S2 characters extract → 🛑 [Tier1 ①] characters.yaml レビュー
    S3 lexicon            → 🛑 [Tier1 ②] lexicon.yaml レビュー
    S4 voice install (auto)

[B] Visual identity
    S5 candidates         → 🛑 [Tier1 ③] candidate 選択
    S7 stylesheets        → 🛑 [Tier1 ④] stylesheet 視認

[C] Scenario
    S8 scenes.json + S10a Codex → 🛑 [Tier2 ⑤] spot-check
    S11 render panels + S12 retry → 🛑 [Tier1 if 3 round 失敗]
    S9 bubbles.json (vision) + S10b Codex → 🛑 [Tier2 ⑥] spot-check

[D] Audio
    S13 voice (3-layer)   → 🛑 [Tier2 ⑦] voice_review.md
    S13b 再合成
    S14/S15 SFX/BGM (auto)

[E] Composition + Video
    S16-S22 (auto)
    →                       🛑 [Tier3 ⑧] 完成動画 1 通し視聴
```

合計の人作業時間: **1 章につき 25〜45 分** (生成自体は数時間〜半日)。

### 最小限版 vs 理想版

| プロファイル | 含むチェック | 所要 | リスク |
|---|---|---|---|
| **最小限 (プロトタイプ用)** | ① + ③ + ⑧ | 15〜20 分 | lexicon 漏れで全 wav 再合成、stylesheet drift で全パネル作り直しの可能性 |
| **理想 (publish 想定)** | ①〜⑧ 全て | 30〜45 分 | 安定運用 |

スキップしてはいけない最小セット = **① characters.yaml + ③ candidate selection + ⑧ 最終視聴**。

### チェック作業を楽にする UI 工夫

人レビューのコストを下げるためにチェックポイント停止メッセージに以下を組み込む:

| Tier | 仕掛け |
|---|---|
| ① ② | yaml をエディタで自動 open (`$EDITOR <path>`) |
| ③ | candidates 4 枚を grid 表示する HTML を生成 → `open http://localhost:8000` |
| ④ | `open <path/to/stylesheet>.png` で macOS Preview に直接送る |
| ⑤ | Codex の review_round_N.md を `glow` か `bat` で整形表示 |
| ⑥ | 重要パネル N 枚だけ bubbled.png を生成して並べ open |
| ⑦ | `voice_review.md` を `[y/n]` インタラクティブ プロンプトで自動 lexicon マージ |
| ⑧ | `mpv --speed=1.5` で倍速視聴 + ループ位置メモ |

`pipeline.py` のチェックポイント停止メッセージに「次に実行すべきコマンド」を必ず print する (人がコマンドを思い出さずに済むように)。

---

## 13. レビュー desktop アプリ (M9)

CLI と §12 の `$EDITOR` ベースのチェックでは限界がある作業 — 音声を聴いて lexicon に追加、bubble をドラッグして位置調整、コメント付きで Claude に再生成依頼 — を 1 つのアプリに集約する。**Claude Code 主導は変えない**。アプリは「人がチェック・微調整するための前線基地」であり、再生成は

- **直接実行できるもの** (Claude を介さない): voice 再合成 / bubble PIL 再描画 / SFX/BGM 再生成 / 音声 mix / 動画再エンコード
- **Claude 介在が必要なもの**: scenes.json / bubbles.json / characters.yaml の意味的な書き換え、パネル画像生成プロンプトの調整

の 2 経路を内蔵する。

### 13.1 設計目標

1. **Claude Code を中央にしたまま** — pipeline.py を引き続き正本。アプリは pipeline.py が書いた成果物を読み、限定的な再生成/書き戻しのみ
2. **コメント = タスク** — 人がコメントを書くと、それが review 履歴に残り、`@claude` タグ付きならタスクキューに入る
3. **直接再生成は数秒で** — voice/bubble などの差し替えは「Claude を起こす」コストを払わない
4. **Single project, single chapter** が基本単位 — 複数章を並行表示はしない (チャプター切替は左サイドバーから)
5. **完全ローカル** — クラウドサーバ不要、Aivis/ElevenLabs/Gemini のキーは既存の `.env`

### 13.2 アーキテクチャ

```
                    ┌─────────────────────────┐
                    │   pipeline.py (CLI)     │
                    │   既存。S0〜S22         │
                    └──────────┬──────────────┘
                               │ writes
                               ▼
              ┌────────────────────────────────────┐
              │  projects/<id>/work/chapters/<ch>/ │
              │   scenes.json / bubbles.json       │
              │   panels/ / audio/ / bubbled/ ...  │
              │   review_state.json   ← NEW        │
              │   comments/<panel>.md ← NEW        │
              │   claude_tasks.jsonl  ← NEW (queue)│
              └──────────┬─────────────────────────┘
                         │ reads / writes
                         ▼
       ┌──────────────────────────────────────────┐
       │  Desktop app (FastAPI + Web frontend)    │
       │  ├─ /api/* REST endpoints                │
       │  ├─ /ws WebSocket (live regen progress)  │
       │  └─ static SPA (Svelte/React)            │
       └────────┬───────────────────┬─────────────┘
                │ direct regen      │ claude task
                ▼                   ▼
        ┌──────────────┐    ┌──────────────────────┐
        │ Aivis / PIL  │    │ Claude Code 起動 (-p)│
        │ ffmpeg /     │    │ comments を読んで    │
        │ ElevenLabs   │    │ scenes/bubbles 修正  │
        └──────────────┘    └──────────────────────┘
```

**バックエンド**: FastAPI (Python)。pipeline.py の各モジュール (`render_panels`, `narrate`, `audio_mixer` 等) を関数として直接呼ぶ。

**フロントエンド**: 静的 SPA。推奨は Svelte + Vite (バンドルが小さい)。React でも可。

**起動**:
```bash
uv run python -m src.desktop_app                # localhost:8765 を browser で
uv run python -m src.desktop_app --webview      # pywebview で native window
```

将来的に Tauri (Rust shell) で .app パッケージ化、これは M9d。

### 13.3 主要画面

#### (a) Chapter timeline (左サイドバー + メイン)
- 左: project / chapter ツリー
- メイン: 章のパネル一覧を縦スクロールで一望
- 各パネルに状態 icon: ✓ approved / ⚠ has comments / ✗ regen pending / 🔄 regenerating / ⏸ awaiting human
- 章全体の完成動画を埋め込み player で頭出し再生 (各 panel をクリックで該当時刻へ jump)

#### (b) Panel detail view
1パネルを選ぶと詳細画面に遷移:

```
┌──────────────────────────────────────────────────────────┐
│ scene_03_p02   [💾 save] [🔄 regen panel] [🤖 ask claude] │
├────────────────────┬─────────────────────────────────────┤
│                    │ Bubbles                              │
│  panel image with  │ ┌──────────────────────────────────┐ │
│  bubble overlay    │ │ #1 narration  speaker=narrator   │ │
│  (drag to move)    │ │  text: "ああ、そうか..."         │ │
│                    │ │  pos: x=70%, y=8%   width=26%    │ │
│                    │ │  [▶ play] [🔄 resynth] [💬 ...]  │ │
│                    │ ├──────────────────────────────────┤ │
│                    │ │ #2 speech  speaker=takeichi      │ │
│                    │ │  text: "わざ、と"                │ │
│                    │ │  whisper: "わざと"  ⚠ similarity 0.92│
│                    │ │  [▶ play] [🔄 resynth] [💬 ...]  │ │
│                    │ └──────────────────────────────────┘ │
│                    │ SFX / BGM                            │
│                    │  sfx_01: distant cicadas  [▶][🔄]   │
│                    │  scene bgm: ambient drone [▶][🔄]   │
│                    │ Comments                             │
│                    │  - 葉蔵の表情をもう少し虚ろに [@claude]│
└────────────────────┴─────────────────────────────────────┘
```

#### (c) Bubble editor (panel detail の中)
- バブルをドラッグして位置移動 (リアルタイムで `x_pct/y_pct` 反映)
- リサイズハンドルで `width_pct` 変更
- ダブルクリックでテキストインライン編集
- 変更すると save ボタンが点灯 → save で bubbles.json 更新 + PIL 再レンダリングを直接実行 (Claude 不要、1秒)

#### (d) Audio review pane
- bubble 単位で wav 再生
- waveform 表示 (wavesurfer.js)
- whisper transcript と意図テキストの diff 表示 (赤で不一致部分ハイライト)
- 「✏️ 読み修正」ボタン → 該当 surface と reading の入力モーダル → lexicon.yaml に追加 + その bubble だけ Aivis で再合成 (Claude 不要)
- voice_review.md の内容もここに集約

#### (e) Comment pane
- panel/bubble/scene 単位でコメント可
- マークダウン記法
- `@claude` タグ付きコメントは `claude_tasks.jsonl` にエンキュー
- タスク状態 (pending / running / done) をリアルタイム表示

#### (f) Lexicon manager
- `lexicon.yaml` のテーブル編集 (surface / reading / kind)
- voice_review.md の自動提案を承認/却下するインタフェース (一括 OK ボタン)

#### (g) Final QA viewer
- `output/<ch>/webtoon_scroll.mp4` を 1.5x 倍速埋め込み
- 各パネル境界で chapter mark
- 気になった瞬間に "🚩 mark" すると panel detail に jump できる

### 13.4 再生成の分類

#### Claude 不要 (アプリが直接 Python 関数を呼ぶ、数秒で完了)

| 操作 | バックエンド呼び出し | 影響範囲 |
|---|---|---|
| voice 再合成 (lexicon 更新後) | `narrate.synthesize_panel(...)` | 1 bubble |
| bubble 位置/サイズ/フォント変更 | `bubble_renderer.render_bubbles_on_panel(...)` | 1 panel |
| SFX 再生成 (prompt 変更) | `synth_sfx.synthesize(...)` | 1 SFX |
| BGM 再生成 (prompt 変更) | `synth_bgm.synthesize_loop(...)` | 1 scene |
| 音声 mix 再実行 (ducking 調整) | `audio_mixer.mix_panel(...)` | 1 panel |
| webtoon 縦結合再実行 | `compose_webtoon.compose_chapter(...)` | 1 chapter |
| 動画再エンコード (target 変更) | `scroll_video.build(...)` | 1 chapter |

これらは UI の `🔄` ボタンに直結。クリック → progress バー → 完了通知。

#### Claude 介在 (タスクキュー経由、数十秒〜数分)

| 操作 | Claude に渡すもの | 影響範囲 |
|---|---|---|
| パネル画像の再生成 (フィードバック付き) | comment + 当該 panel.json | 1 panel |
| scenes.json の意味的修正 (シーン分割など) | comment + scenes.json + chapter novel.txt | 章の一部 panels |
| bubbles.json の本格書き直し | comment + bubbles.json + 当該 panels の画像 | 章の一部 |
| characters.yaml の追記/修正 | comment + characters.yaml + novel.txt | 全 chapter (caution) |
| lexicon.yaml の自動拡充 | voice_review.md + lexicon.yaml | 全 chapter |

これらは UI の `🤖 ask claude` ボタン。クリック → comment 入力モーダル → `claude_tasks.jsonl` にエンキュー → バックグラウンドで `claude -p` 起動 → 完了したら WebSocket 経由でアプリに通知。

### 13.5 データフロー: review_state.json と comments/

#### `review_state.json` (アプリが管理)
パネルごとのレビュー状態を 1 ファイルで管理:

```jsonc
{
  "chapter_id": "chapter_01",
  "panels": {
    "scene_01_p01": {
      "status": "approved | has_comments | regen_pending | regenerating",
      "last_reviewed_at": "2026-05-10T10:23:00Z",
      "approved_by_human": true,
      "voice_verified": true,           // Whisper 類似度 OK
      "image_quality_passed": true,     // S12 で OK
      "open_comments": 0,
      "claude_tasks": []                // claude_tasks.jsonl の id 参照
    }
  }
}
```

#### `comments/<panel_id>.md` (人とアプリが共有、Claude も読む)
パネルあたり 1 ファイル、append-only:

```markdown
## 2026-05-10 11:42  user
panel image: 葉蔵の左側にあるべきドアが右側になっている
@claude regenerate-panel

## 2026-05-10 11:43  app
queued task: claude_task_0042

## 2026-05-10 11:51  claude
prompt 修正: "the door is on the LEFT side of the frame, opposite the boy"
re-rendered panels/scene_03/scene_03_p02_best.png
```

#### `claude_tasks.jsonl` (タスクキュー、append-only)
```jsonl
{"id":"claude_task_0042","ts":"2026-05-10T11:42","type":"regenerate-panel","panel_id":"scene_03_p02","comment_path":"comments/scene_03_p02.md","status":"pending"}
{"id":"claude_task_0042","ts":"2026-05-10T11:43","status":"running"}
{"id":"claude_task_0042","ts":"2026-05-10T11:51","status":"done","artifacts":["panels/scene_03/scene_03_p02_best.png"]}
```

### 13.6 API 設計 (FastAPI 主要 endpoint)

```
GET  /api/projects                              # 一覧
GET  /api/projects/{id}/chapters                # 章一覧 + review_state サマリ
GET  /api/projects/{id}/chapters/{ch}           # scenes.json + bubbles.json + review_state
GET  /api/projects/{id}/chapters/{ch}/panels    # パネル一覧 (縮小画像 + 状態)
GET  /api/projects/{id}/chapters/{ch}/panels/{pid}  # 1 パネル詳細

# パネル/バブル画像
GET  /api/static/projects/{id}/.../panels/.../*_best.png         # 静的配信
GET  /api/static/projects/{id}/.../bubbled/.../*_bubbled.png

# 音声配信 + transcript
GET  /api/audio/{id}/{ch}/voice/{pid}.wav
GET  /api/audio/{id}/{ch}/voice/{pid}/transcript                  # whisper結果 + similarity

# 直接再生成 (Claude 不要)
POST /api/regen/voice         body={pid, bubble_idx, lexicon_addition?}
POST /api/regen/bubble        body={pid, bubble_idx, x_pct, y_pct, width_pct, font_size_pt, text?}
POST /api/regen/sfx           body={pid, sfx_id, prompt}
POST /api/regen/bgm           body={scene_id, prompt}
POST /api/regen/mix           body={pid, ducking_params}
POST /api/regen/webtoon       body={chapter_id}
POST /api/regen/video         body={chapter_id, target}

# Claude タスク
POST /api/claude/queue        body={panel_id?, scene_id?, type, comment}
GET  /api/claude/tasks        # キュー一覧
GET  /api/claude/tasks/{tid}  # ステータス + 結果

# コメント
GET  /api/comments/{pid}
POST /api/comments/{pid}      body={author, text, mention_claude:bool}

# Lexicon
GET  /api/projects/{id}/lexicon
POST /api/projects/{id}/lexicon  body={surface, reading, kind}

# WebSocket (進捗・通知)
WS   /ws  → server push: {type: "regen_progress" | "claude_task_done" | ...}
```

### 13.7 Claude タスクランナーの実装

`src/desktop_app/claude_runner.py`:

```python
import json, subprocess, time
from pathlib import Path

def run_pending_tasks(project_dir: Path):
    tasks_file = project_dir / "work" / "claude_tasks.jsonl"
    while True:
        pending = [t for t in load_tasks(tasks_file) if t["status"] == "pending"]
        for task in pending:
            mark_status(tasks_file, task["id"], "running")
            try:
                run_one(project_dir, task)
                mark_status(tasks_file, task["id"], "done")
            except Exception as e:
                mark_status(tasks_file, task["id"], "failed", error=str(e))
        time.sleep(2)

def run_one(project_dir, task):
    # task type 別にプロンプトを組み立てて claude -p に渡す
    if task["type"] == "regenerate-panel":
        comment_path = project_dir / "work" / "chapters" / task["chapter_id"] / task["comment_path"]
        prompt = f"""Read the comment at @{comment_path}.
        The user wants to regenerate panel {task['panel_id']}.
        1. Read scenes.json to find the panel's current spec.
        2. Adjust the panel spec based on the comment (don't rewrite unrelated panels).
        3. Trigger render_panels.render_panel() for that panel only.
        4. Append a confirmation line to {comment_path}.
        """
        subprocess.run(["claude", "--dangerously-skip-permissions", "-p", prompt], check=True)
    elif task["type"] == "rewrite-scenes":
        ...
```

このランナーをアプリ起動時にバックグラウンド子プロセスとして立ち上げる。

### 13.8 実装フェーズ (M9 内訳)

| フェーズ | 内容 | 所要 (目安) |
|---|---|---|
| M9a | read-only viewer | 章/パネル/バブル/音声/動画を表示。データ書き戻しなし | 2〜3 日 |
| M9b | direct regen | voice / bubble / SFX / mix の再生成ボタン。lexicon 編集。Claude 介在なし | 3〜5 日 |
| M9c | comments + Claude タスク | コメント機能 + claude_tasks.jsonl + claude_runner | 3〜4 日 |
| M9d | polish / 配布 | pywebview / Tauri パッケージ化、複数プロジェクト切替、settings UI | 2〜4 日 |

合計の目安 10〜16 日。M9a だけでも有用 (見るだけでもチェックが楽になる)、M9b で大半の微調整がカバー、M9c で本格的な再生成サイクル。

### 13.9 技術スタックの推奨

| 層 | 推奨 | 代替 |
|---|---|---|
| バックエンド | FastAPI | Flask, Starlette |
| フロントエンド | **Svelte + Vite + TypeScript** | React, Vue |
| UI ライブラリ | TailwindCSS + shadcn-svelte | Mantine, MUI |
| 画像/canvas 操作 | Konva.js (バブルドラッグ) | Fabric.js |
| 音声波形 | wavesurfer.js | peaks.js |
| 動画再生 | HTML5 video + Plyr | Video.js |
| 通信 | REST + WebSocket (FastAPI 標準) | tRPC |
| 配布 (M9d) | Tauri (Rust shell) | pywebview, Electron |

Svelte 推奨理由: バンドルが軽い (Tauri と相性良い)、ストア管理がシンプル、reactive な UI が書きやすい。React の方が好みなら React でも問題ない。

### 13.10 既存 webtoon-gen との統合

新規ディレクトリ `src/desktop_app/`:

```
src/desktop_app/
├── server.py              # FastAPI app
├── claude_runner.py       # Claude タスクランナー
├── routes/
│   ├── projects.py
│   ├── panels.py
│   ├── bubbles.py
│   ├── audio.py
│   ├── regen.py           # 直接再生成 endpoints
│   ├── claude.py          # タスクキュー
│   └── lexicon.py
├── services/
│   ├── review_state.py    # review_state.json CRUD
│   ├── comments.py        # comments/*.md CRUD
│   └── tasks.py           # claude_tasks.jsonl CRUD
└── frontend/              # Svelte SPA (build artifact が static/ に出る)
    ├── src/
    └── package.json
```

`pipeline.py` 側に変更は不要 (アプリが pipeline の関数を import するだけ、依存方向は app → pipeline)。

### 13.11 落とし穴

| 罠 | 対策 |
|---|---|
| アプリで bubble 位置を手動編集 → Claude が後で scenes.json 再生成して上書き | comments の `@claude` 指定なしの編集はアプリだけで完結、Claude は触らない原則。アプリの編集が `bubbles.json.<panel>.bubbles[].locked: true` フラグを立てる |
| Claude タスクの並走で同じファイルが衝突 | claude_runner は **直列実行** (シングルスレッド)。並列したいなら panel 単位ロック |
| review_state.json と実ファイル mtime の不整合 | アプリ起動時に rebuild_state() で全 panel の mtime と照合 |
| bubble drag が iframe の中で効かない | Konva.js の Stage は body 直下に配置 |
| WebSocket 切断で進捗ロスト | reconnect 時に `/api/claude/tasks?since=<ts>` でリプレイ |
| 大きい webtoon.png (40 MB) を毎回 reload | アプリは 1080px scaled 版を別キャッシュ (`work/preview/<ch>/webtoon_1080.png`) |
| ffmpeg の subprocess を UI thread でブロック | regen は asyncio + ProcessPoolExecutor、進捗は WebSocket push |
