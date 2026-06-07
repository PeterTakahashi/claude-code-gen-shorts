# 画像生成スケーリング戦略 (2026年版)

## TL;DR

**100x scale = 200 shorts/日 = 1,200画像/日 = 36,000画像/月** 想定。

| ターゲット規模 | 戦略 | 月コスト |
|---|---|---|
| **今 (24本/日)** | Gemini batch + square 1024×1024 + blur-pad | **~$86** |
| **10x (240本/日)** | + reference photo library + FLUX.2 dev multi-ref 混合 | **~$500** |
| **100x (2400本/日)** | M4 Pro local Z-Image Turbo + EcomID/PuLID + cloud fallback | **~$250** |

**直近やる価値あり**: ① reference photo library 構築 ② FLUX.2 [dev] multi-ref を実験 ③ 並行で Draw Things + Z-Image Turbo の local 環境構築

---

## 1. 重要な前提: 「named-entity recognition」が高い壁

**Gemini/OpenAI/Grokだけ** が "Steve Jobs" "Elon Musk" 等の固有名詞だけで顔を描ける。これが現状高コストの理由 ($0.02-0.04/image)。

FLUX / SDXL / Z-Image など安いモデルは:
- **プロンプトのみ** では Jobs に似ない (汎用 anime男性が出る)
- **reference image を1枚渡す** と顔を保持できる (IP-Adapter / InstantID / PuLID / EcomID 等の adapter経由)
- **per-character LoRA** を訓練 ($1-10/人, 1回) すれば 100%精度

→ 結論: **「reference photo library」が安いモデル使用の前提条件**

---

## 2. モデル比較 (2026年5月時点)

| モデル | $/image | 固有名詞 | 一貫性 | 用途 |
|---|---|---|---|---|
| **Nano Banana 2 (Gemini 3.1 Flash Image)** | $0.022 batch | ◎ 自然認識 | ◎ 多被写体5+ | 現状ベスト、premium |
| OpenAI gpt-image-1 medium | $0.042 | ◎ | ○ | バッチなし、コスト高 |
| OpenAI gpt-image-1-mini | ~$0.012 | ○ | ○ | コスパ良いが要検証 |
| **FLUX.2 [dev] multi-ref edit** | **$0.018** | × (ref必須) | ◎ 10 ref slots | refあれば最強コスパ |
| FLUX.2 [pro] multi-ref | $0.045 | × (ref必須) | ◎ | premium quality |
| FLUX.1 Kontext [pro] | $0.04 | × (ref必須) | ◎ 90-95% | やや旧 |
| **Z-Image Turbo (cloud)** | $0.01 | × | △ 6 panel境 | 超安価、雑用に |
| Hunyuan Image 3 | $0.03 | × | ○ | anime score 4.4/5 |
| Qwen-Image-2.0-Pro | $0.075 | × | ◎ edit強い | 中価格帯 |
| SD 3.5 + adapter | $0.008-0.015 | × | adapter次第 | 自由度高 |
| **Self-hosted Z-Image Turbo M4 Pro** | **~$0.005** (電気) | × | adapter次第 | 至高のコスパ、3sec/image |
| Self-hosted FLUX.1 M4 Pro | ~$0.005 | × | ○ | 50sec/image, 速度がbottleneck |

### 固有名詞recognition の代替手段

| 手法 | コスト | 精度 | DX |
|---|---|---|---|
| **Nano Banana 2 名前プロンプト** | $0.022/img | ◎ | ◎ 楽 |
| **FLUX.2 + reference photo** | $0.018/img + ref管理 | ◎ 90-95% | ○ 1人1枚必要 |
| **EcomID** (open, on local FLUX/SDXL) | $0 | ◎ 現行best | △ 自分でinfra |
| **PuLID-Flux** (open) | $0 | ○ パネル間drift注意 | △ |
| **InstantID** (open, SDXL) | $0 | ○ やや旧 | △ |
| **per-character LoRA訓練** | $1-10/人 (1回) | ◎ 100% | △ 50本/character以上で元取れる |

---

## 3. 一貫性 (consistency) の取り方

### 現行 (Nano Banana 2)
- 1プロンプト内で multi-subject 指定 → 5 characters まで一貫描画
- 6 panels間でキャラ顔は自動で揃う (model内部の knowledge)
- 場所一貫性は prompt explicitness 次第

### Reference photo library 構築 (推奨)
1. 主要被写体 50人 (ジョブズ・マスク・井深大 等) について Nano Banana 2 で **canonical portrait 1枚** を生成 ($0.02/人 × 50 = $1)
2. その portrait を `assets/refs/<person_id>.png` に保存
3. FLUX.2 / Z-Image / EcomID 等の cheap model に refとして渡す
4. **一度作れば永続資産** — 以後のすべての panel で再利用

### 場所 / 小物の一貫性
- 重要 location (Apple HQ, SpaceX launch pad, 京都老舗) も同じ手法で 1枚ずつ ref画像生成
- prompt に `[scene: see ref]` で injection

---

## 4. Self-hosting on M4 Pro

**Draw Things** (Native Swift app, Metal FlashAttention 2.0) 推奨 > ComfyUI (20%遅い)

| モデル | M4 Pro 速度 | RAM | 品質 |
|---|---|---|---|
| Z-Image Turbo (6B, 8 steps) | **3秒/image** | 12GB | 中-高 |
| FLUX.1 [dev] (12B) | 50秒/image | 24GB (5-bit) / 48GB (FP16) | 高 |
| SDXL + EcomID | 8秒/image | 8GB | 中 |

**throughput math**: 36,000 imgs/月 → 1,200/日 → 必要 compute time:
- Z-Image: 1,200 × 3s = **60分/日** (1 Mac で余裕)
- FLUX.1: 1,200 × 50s = **17時間/日** (1 Macでギリギリ、3台あれば余裕)

**コスト**: 電気 ~$5/月。実質ゼロ。

**setup 時間**: Draw Things + Z-Image Turbo + EcomID, 1日でセットアップ可能。

---

## 5. Phased Roadmap

### Phase 1 (今〜2x scale, 400 imgs/日)
- **Gemini batch + square 1024×1024 + blur-pad** (現行)
- 月コスト: **~$86**
- new: reference library 構築開始 (1人ずつ canonical portrait を保存)

### Phase 2 (10x scale, 12k imgs/月)
- **50%は Gemini batch** (固有名詞要件のあるもの)
- **50%は FLUX.2 [dev] multi-ref** with reference library ($0.018/img)
- 月コスト: **~$500** (vs Gemini fullだと $720)
- client work: FLUX.2 dev で「客の写真→shorts」を即対応 ($0.018/img、margin高)

### Phase 3 (100x scale, 36k imgs/月) + 多客対応
- **Self-hosted Z-Image Turbo on M4 Pro 64GB** + Draw Things + EcomID
- **cloud fallback**: Nano Banana 2 (固有名詞専用) + FLUX.2 [dev] (refあるがlocal品質不足のもの)
- 月コスト: **~$250** (local $5 + cloud overflow $200)
- client work tier:
  - 「Fast tier」($0.018/img, FLUX.2 dev): 客写真→当日納品
  - 「Premium tier」($5-10 one-time per LoRA + $0.025/img): 大型客向けLoRA訓練→以後高精度
- 月margin: **client 1件 $300 でも複数件回せる**

---

## 6. 直近で実行する3つのexperiment

1. **FLUX.2 [dev] multi-ref で 1本 short build**
   - reference: Gemini で作った jobs portraitを ref として使う
   - cost: 6 panels × $0.018 = **$0.11/short** (vs Gemini batch $0.12 ≈ 同等)
   - 品質比較

2. **Self-hosted Z-Image Turbo on M4 Pro**
   - Draw Things install + Z-Image Turbo モデル download
   - 同じ panel を生成して品質+速度測定
   - 品質OKなら → local default に切替

3. **Reference photo library の構築開始**
   - 既存20+人物について Gemini で 1枚ずつ canonical portrait生成
   - `assets/refs/<person_id>.png` 配置
   - 今後 FLUX.2 / local model に渡せる準備

---

## 7. Gotchas (重要注意)

- **EU AI Act 2026年8月施行**: deepfake 表示義務。Jobs/Musk等の biography content は「これは AI 生成」表示が必要かも (全 approach に共通)
- **PuLID-Flux drift**: パネル間で顔がドリフトすることが多い → seed固定 + 単一reference image を使う
- **Z-Image Turbo の長尺一貫性**: visual novel 50+ images では崩れる、6 panel shorts は OK
- **M4 Pro 64GB RAM**: 64GB あれば FLUX.1 FP16 が走る、32GBだと 5-bit/8-bit 量子化必須
- **YouTube quota**: 100x scale で 200 uploads/日 × 1600 = 320,000 units/日 → **Google Cloud project が100個必要** (1projectあたり10K limit)

---

## 出典

- [FLUX.2 [pro] multi-ref edit](https://fal.ai/models/fal-ai/flux-2-pro/edit)
- [FLUX.1 Kontext [pro] on fal.ai](https://fal.ai/models/fal-ai/flux-pro/kontext)
- [Nano Banana 2 pricing](https://openrouter.ai/google/gemini-3.1-flash-image-preview)
- [Draw Things vs ComfyUI on M4](https://www.heyuan110.com/posts/ai/2026-02-15-mac-mini-local-image-generation/)
- [PuLID vs InstantID vs EcomID 比較](https://myaiforce.com/flux-pulid-vs-ecomid-vs-instantid/)
- [Z-Image Turbo Anime LoRA on Civitai](https://civitai.com/models/2259646/z-image-turbo-anime)
- [Hunyuan Image 3 vs 2](https://blog.fal.ai/hunyuan-image-3-0-vs-2-0-upgrading-your-genai-image-generator/)
- [Black Forest Labs pricing](https://bfl.ai/pricing)
- [AI image API pricing 2026 - DigitalApplied](https://www.digitalapplied.com/blog/ai-image-generation-api-pricing-comparison-2026)
