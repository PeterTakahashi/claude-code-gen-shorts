# Webtoon Generator — SPEC

小説テキストから縦スクロール型webtoonを自動生成するパイプライン。
Claude Code（サブスク）がオーケストレーター兼LLM/VLM評価者を兼ねる。
画像生成のみ外部API（Gemini 2.5 Flash Image = nanobanana）を使う。

---

## 0. 前提

- Claude Code CLI が起動していること（このSPEC.mdをそのまま読ませて実装・実行させる想定）
- `GEMINI_API_KEY` が環境変数に設定されていること（唯一の外部API key）
- Python 3.11+ / `uv` 推奨
- 初回ターゲット: 太宰治『人間失格』第一の手記（青空文庫・著作権切れ）

**Claude Codeに任せる範囲**
- シナリオ分解、キャラ抽出、構図設計、プロンプト組み立て、生成画像の評価、リトライ判断、吹き出し配置設計、最終合成
- 画像生成は Gemini API を叩くだけ。VLM評価は Claude Code が画像を直接 `Read` して行う（API keyなしで完結）

---

## 1. ディレクトリ構成

```
project/
├── SPEC.md                      # これ
├── pyproject.toml
├── .env                         # GEMINI_API_KEY
├── src/
│   ├── config.py                # パス/モデル名/閾値
│   ├── novel_loader.py          # 青空文庫テキスト取得・ルビ除去
│   ├── scene_decomposer.py      # 小説 → beats.json
│   ├── character_extractor.py   # 登場人物抽出 → characters.json
│   ├── character_designer.py    # キャラ候補4枚生成
│   ├── style_sheet.py           # 選択キャラの表情/ポーズ固定
│   ├── scene_director.py        # beatごとの構図・視線設計
│   ├── prompt_composer.py       # 視覚文法 → 英語プロンプト
│   ├── image_generator.py       # nanobanana呼び出し(best-of-N)
│   ├── critic.py                # Claude Code自身が評価する指示書を返す
│   ├── retry_controller.py      # 失敗理由→プロンプト摂動
│   ├── bubble_layout.py         # 吹き出し位置設計
│   ├── composer.py              # Pillowで吹き出し合成＋縦結合
│   └── selector_ui.py           # キャラ選択HTML生成
├── assets/
│   ├── fonts/                   # 源暎アンチック等
│   └── refs/                    # 時代考証用の参考画像
├── work/
│   ├── novel.txt
│   ├── beats.json
│   ├── characters.json
│   ├── characters/
│   │   └── yozo/
│   │       ├── candidates/      # 候補4枚
│   │       ├── selected.png
│   │       └── stylesheet.png
│   ├── panels/
│   │   └── beat_001/
│   │       ├── panel_01_v1.png
│   │       ├── panel_01_v2.png
│   │       ├── panel_01_best.png
│   │       └── critique.json
│   └── bubbles/
└── output/
    └── chapter_01.png           # 最終webtoon画像（縦長）
```

---

## 2. パイプライン

各ステージは独立したPythonモジュールとして実装し、中間成果物をJSON/PNGでディスクに落とす。
Claude Codeは各ステージを順に実行し、途中で画像を読んで評価→リトライ判断をする。

### Stage 1: 小説ロード (`novel_loader.py`)
- 青空文庫URL or ローカルtxtを入力
- ルビ記法 `《...》`、注記 `［...］` を除去
- 段落単位でリスト化

### Stage 2: シーン分解 (`scene_decomposer.py`)
Claude Code自身が小説を読んで、ビート（2〜4コマ単位の意味まとまり）に分解する。

**出力: `beats.json`**
```json
{
  "beats": [
    {
      "id": "beat_001",
      "source_text": "対応する小説の抜粋",
      "setting": {
        "location": "葉蔵の家・縁側",
        "time_of_day": "夕方",
        "era": "昭和初期"
      },
      "characters_present": ["yozo_child"],
      "beat_type": "establishing" | "reaction" | "action" | "monologue" | "dialogue" | "climax",
      "emotional_arc": "無邪気な道化 → 底にある虚無がよぎる",
      "panels": [
        {
          "panel_id": "beat_001_p01",
          "panel_type": "wide_establishing",
          "intent": "昭和初期の縁側を確立",
          "duration_hint": "long"
        },
        {
          "panel_id": "beat_001_p02",
          "panel_type": "close_up",
          "intent": "葉蔵の道化の笑みを捉える"
        },
        {
          "panel_id": "beat_001_p03",
          "panel_type": "extreme_close_up_eyes",
          "intent": "笑みの下の暗い目"
        }
      ]
    }
  ]
}
```

**内的独白が多い人間失格特有の型:**
- `beat_type: "monologue"` → 背景ぼかし・表情主体・テキスト量多め
- `emotional_arc` は必ず明記（表情指示の根拠になる）

### Stage 3: キャラ抽出 (`character_extractor.py`)
Claude Code自身が小説全体を読んで登場人物リストを作る。

**出力: `characters.json`**
```json
{
  "characters": [
    {
      "id": "yozo",
      "name_ja": "大庭葉蔵",
      "age_variants": ["child_6", "teen_16", "adult_25"],
      "visual_spec": {
        "build": "痩身、やや猫背",
        "hair": "黒髪・短髪・やや乱れ",
        "eyes": "切れ長・瞳は暗い",
        "face": "端正だが陰がある",
        "default_expression": "作り笑いの下に虚無",
        "clothing_era": "昭和初期",
        "clothing_default": "着物 or 書生風学生服"
      },
      "personality_for_expression": "道化を演じる / 内面は恐怖と罪悪感"
    }
  ]
}
```

### Stage 4: キャラデザイン候補生成 (`character_designer.py`)
各キャラ・各年齢バリアントにつき **4枚の候補** を生成。

**プロンプトテンプレ:**
```
Character sheet reference, front view, neutral expression, full body,
{visual_spec を英訳展開},
{era考証: "early Showa era Japan, 1920s-1930s"},
monochrome webtoon style, clean line art, subtle screentones,
plain white background, studio lighting, high detail
```

4枚はseed違いで同時生成。アスペクト比は 3:4 固定。

### Stage 5: ユーザー選択UI (`selector_ui.py`)
- `work/characters/{id}/candidates/` の4枚を並べたHTMLを生成
- `python -m http.server 8000 &` で自動サーブ → `open http://localhost:8000/...`
- ユーザーはブラウザで確認 → **チャットに番号で応答**（例: "yozo_child: 2, yozo_teen: 4"）
- Claude Codeは応答を受けて `selected.png` にコピー

**HTMLは簡素で良い:**
```html
<div class="grid">
  <div><img src="candidate_1.png"><p>1</p></div>
  <div><img src="candidate_2.png"><p>2</p></div>
  <div><img src="candidate_3.png"><p>3</p></div>
  <div><img src="candidate_4.png"><p>4</p></div>
</div>
```

### Stage 6: スタイルシート生成 (`style_sheet.py`)
選択されたキャラについて、**表情12種 × 全身4方向**のグリッド画像を生成し固定する。
以降の全コマ生成で、このシートを参照画像として毎回添付する（キャラ同一性の肝）。

表情: 無表情 / 作り笑い / 本当の笑い / 恐怖 / 絶望 / 困惑 / 怒りを抑えた顔 / 涙 / 泥酔 / 虚無 / 驚愕 / 諦念
方向: 正面 / 斜め45° / 横顔 / 後ろ姿

### Stage 7: 構図設計 (`scene_director.py`)
各パネルに視覚文法スキーマを付与する。Claude Code自身が担当。

**出力スキーマ（各パネルに追加される）:**
```json
{
  "panel_id": "beat_001_p02",
  "shot_type": "close_up",
  "camera_angle": "slight_low",
  "eye_line": "camera",
  "composition": "rule_of_thirds_left",
  "focal_point": "yozo_child_face",
  "emotion_primary": "performative_smile",
  "emotion_secondary": "hollow_eyes",
  "lighting": "soft_window_light_from_right",
  "background_style": "blurred_engawa",
  "distance_to_prev_panel": "tight",
  "distance_to_next_panel": "breath",
  "aspect_ratio": "4:5",
  "characters_in_panel": [
    {"id": "yozo_child", "pose": "sitting_seiza", "direction": "facing_camera"}
  ]
}
```

**ビート内の連続性ルール（scene_directorで強制）:**
- eye_line が右なら次コマの focal_point は右寄せ or 視線の先に被写体
- 180度ラインを跨がない
- beat_type が `monologue` のパネルは背景抽象化・焦点は表情のみ
- ビートのクライマックスパネルは前後より aspect_ratio を縦に伸ばす（1:2など）

### Stage 8: プロンプト合成 (`prompt_composer.py`)
視覚文法スキーマを英語プロンプトに展開。

**テンプレ:**
```
{shot_type}, {camera_angle} angle, {composition} composition,
subject: {character_description_from_stylesheet}, {pose}, {facing_direction},
expression: {emotion_primary}, with undertone of {emotion_secondary},
eye line: {eye_line},
setting: {location}, {time_of_day}, {era} Japan,
lighting: {lighting},
background: {background_style},
style: monochrome webtoon, clean linework, subtle screentone shading,
aspect ratio: {aspect_ratio},
negative: text, speech bubbles, watermark, extra fingers, distorted face
```

nanobanana呼び出し時、**参照画像**として以下を常に添付:
1. キャラのstylesheet.png
2. 直前のpanel（best選出済み）— 連続性のため
3. 時代考証用の参考画像（必要なら）

### Stage 9: 画像生成 (`image_generator.py`)
Gemini API (model: `gemini-2.5-flash-image`) を叩く。
各パネルについて **seed違いでN=4枚** を並列生成。

```python
from google import genai
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
# マルチモーダル入力: [プロンプトテキスト, 参照画像1, 参照画像2, ...]
```

出力は `work/panels/{beat_id}/{panel_id}_v{1..4}.png`

### Stage 10: 評価 (`critic.py`)
**Claude Code自身が**生成された4枚の画像を `Read` ツールで直接見て、以下のルーブリックで採点する。
（`critic.py`は実際にはルーブリックと採点先ファイルパスを返すだけのヘルパー。採点はClaude Codeがインタラクティブに実施）

**ルーブリック（各0〜10点、および致命欠陥フラグ）:**
1. `character_identity`: スタイルシートとの一致度
2. `shot_compliance`: 指定ショットタイプの達成
3. `eye_line_accuracy`: 視線方向の正確性
4. `emotion_expressiveness`: 感情の説得力
5. `composition_continuity`: 前パネルとの連続性
6. `era_authenticity`: 時代考証
7. `fatal_flaw`: 指/顔/手の破綻（bool）

**出力: `critique.json`**
```json
{
  "panel_id": "beat_001_p02",
  "candidates": [
    {
      "version": 1,
      "scores": {"character_identity": 8, "shot_compliance": 9, ...},
      "total": 48,
      "fatal_flaw": false,
      "notes": "視線がやや下に外れている"
    }
  ],
  "best_version": 3,
  "best_total": 52,
  "needs_retry": false
}
```

**閾値:**
- 合計点 `< 42` または `fatal_flaw == true` → リトライ
- そうでなければ `panel_XX_best.png` として採用

### Stage 11: リトライ制御 (`retry_controller.py`)
失敗項目に応じてプロンプトを摂動する条件分岐:

| 失敗項目 | 摂動 |
|---|---|
| character_identity 低 | スタイルシートの重み強調、キャラ記述を細部まで展開 |
| shot_compliance 低 | shot_type を明示的に冒頭に配置、aspect_ratio強調 |
| eye_line_accuracy 低 | "looking directly at {direction}, eyes clearly visible" を追加 |
| emotion_expressiveness 低 | 表情記述を2段階詳細化、micro-expression語彙追加 |
| composition_continuity 低 | 前パネルを参照画像に追加 or 重み変更 |
| fatal_flaw | seed大幅変更＋"anatomically correct hands" 強化 |

最大3ラウンド。3ラウンドfailならビート構成自体を見直すフラグ（Claude Codeがパネル分割/統合を提案）。

### Stage 12: 吹き出しレイアウト (`bubble_layout.py`)
Claude Code自身が、採用パネル画像を見て吹き出し配置を設計する。

**出力スキーマ:**
```json
{
  "panel_id": "beat_001_p02",
  "bubbles": [
    {
      "type": "speech" | "thought" | "narration" | "monologue_box",
      "text": "ああ、そうか、この人たちも、笑っているのだ。",
      "position": {"x_pct": 15, "y_pct": 10},
      "width_pct": 40,
      "tail_target": {"x_pct": 40, "y_pct": 60},
      "font": "源暎アンチック",
      "font_size_pt": 14,
      "vertical_text": true
    }
  ]
}
```

**配置ルール:**
- 人物の顔・焦点を吹き出しで隠さない
- 読み順は右上→左下（縦書き日本語のwebtoon慣例）
- モノローグは角丸四角 or ボックスで差別化
- 重要なモノローグはパネル外（黒帯）に配置することも

### Stage 13: 最終合成 (`composer.py`)
- Pillow で各パネルに吹き出しを描画
- パネル間に「間」を入れてビート単位で縦結合
- `beat_type` に応じて間隔調整: `monologue` 後は広く、アクションシーケンスは詰める
- 全ビートを結合して `output/chapter_01.png` 生成（webtoon形式、幅800px固定、高さ可変）

**間隔指針:**
- `distance_to_next_panel: "tight"` → 20px
- `"breath"` → 80px
- `"jump"` → 200px（場面転換）

---

## 3. 設定 (`config.py`)

```python
GEMINI_MODEL = "gemini-2.5-flash-image"
N_CANDIDATES_PER_PANEL = 4
N_CANDIDATES_PER_CHARACTER = 4
SCORE_THRESHOLD = 42
MAX_RETRY_ROUNDS = 3
WEBTOON_WIDTH_PX = 800
DEFAULT_ASPECT_RATIOS = {
    "wide_establishing": "16:9",
    "medium": "4:5",
    "close_up": "4:5",
    "extreme_close_up_eyes": "2:1",  # 横長インパクト
    "full_body": "3:4",
    "climax": "1:2"  # 縦長
}
FONT_PATH = "assets/fonts/GenEiAntiqueNv5-M.ttf"
```

---

## 4. 実行順序（Claude Codeがこの順に進める）

1. 環境確認: `.env` に `GEMINI_API_KEY` があるか
2. `novel_loader` で人間失格・第一の手記を取得
3. `scene_decomposer` で beats.json 生成（Claude Code自身が担当）
4. `character_extractor` で characters.json 生成（同上）
5. `character_designer` で各キャラ・各年齢の候補4枚生成
6. `selector_ui` でHTML生成＋ローカルサーブ
7. **ユーザー待ち**: ブラウザで確認→チャットで選択番号入力
8. `style_sheet` で選択キャラのスタイルシート生成
9. `scene_director` で全パネルに視覚文法付与（Claude Code自身が担当）
10. ビート単位でループ:
    - `prompt_composer` → `image_generator` (best-of-4) → Claude Codeが採点 → 必要ならretry
    - `bubble_layout` をClaude Codeが設計
11. 全パネル完成後、`composer` で最終webtoon生成
12. `output/chapter_01.png` を `present_files` で提示

---

## 5. 人間失格特有の注意

- **道化の笑み**: スタイルシートで「作り笑い」と「本当の笑い」を別枠で固定する。混同すると原作の味が消える
- **目の描写**: 葉蔵の目は「暗い」「底が見えない」が頻出。extreme_close_up_eyes のパネル型を積極活用
- **モノローグ比率**: 第一の手記は7割がモノローグ。monologue_box を多用する想定でレイアウトを組む
- **時代考証語彙**: 「縁側」「書生」「カフェー」「円タク」「銘仙」「羽織袴」などは英訳時に具体描写に展開する（例: 縁側 → "traditional Japanese engawa veranda with wooden floorboards"）
- **モノクロ基調**: 作品のトーンに合わせてモノクロ固定。スクリーントーンで陰影

---

## 6. 最初のマイルストーン

いきなり1章全部やらず、段階的に動作確認する:

**M1**: 最初の1ビート（3パネル）だけ、キャラはデフォルト設定で、評価/リトライなしで生成して縦結合まで通す → パイプラインの骨が動くか確認

**M2**: キャラ選択UIを入れて、スタイルシート使う版にアップグレード

**M3**: 評価＋リトライを入れて、品質閾値を機能させる

**M4**: 吹き出し合成まで入れて完成形

**M5**: 第一の手記全体を通して生成

Claude Codeへの最初の指示は「SPEC.mdのM1だけやって」くらいの粒度で。

---

## 7. コスト見積もり

- nanobanana: 約$0.039/枚
- M1: 3パネル × 4候補 = 12枚 ≒ $0.5
- 1章完走（50パネル × 4候補 × 平均1.5ラウンド）= 300枚 ≒ $12
- Claude Codeはサブスクなので実行時間以外の追加コストなし

---

## 8. 依存ライブラリ（pyproject.toml）

```toml
[project]
dependencies = [
  "google-genai>=0.3.0",
  "pillow>=10.0",
  "python-dotenv",
  "httpx",
  "pydantic>=2.0"
]
```
