# asr-benchmark

**用你自己的資料，測你自己該用哪個語音辨識模型。**

官方 benchmark 是官方的考卷，不一定考你在乎的東西。這個 repo 是一把尺：**不需要人工精修的黃金標準逐字稿**，就能比較不同 ASR 模型／設定在**你的**錄音上的表現。

📝 完整的實測過程與心得：[我的資料，我的 benchmark：幫演講筆記系統換一顆語音辨識引擎](https://drpwchen.com/posts/my-data-my-benchmark/)

---

## 為什麼需要這個

我有一條把演講錄影變成筆記的流水線：**錄影 → 逐字稿 → 對應投影片 → 生成筆記**。

大家的注意力通常都在最後那一步（要用哪個 AI 整理），但整條線的天花板其實在第一步。**語音辨識聽錯多少，後面每一層筆記就錯多少。** 而且它不是聽不懂就留白，它會直接**發明一個不存在的字**給你：`motibra`、`grutius`、`idioma`。

要換掉這顆引擎，就得先有一把尺。

## 這把尺怎麼運作

最理想的標準是人工精修過的逐字稿。但大部分人沒有，也不會為了測試去精雕一份。

替代方案：**用你領域的文獻建一本字典**，然後問模型吐出來的每個字一個很基本的問題 ——

> 這個字在我的領域文獻裡真的存在，還是模型自己掰的？

由此得到兩個數字，**必須一起看**，因為它們往兩個相反的方向壞掉：

| 指標 | 意思 | 抓什麼失敗 |
|---|---|---|
| **precision** | 模型吐出的英文詞裡，有幾成是真的存在的字 | 抓幻覺：模型發明的垃圾字 |
| **capture** | 總共抓到幾個「不重複的真實詞彙」 | 抓漏聽：一個乾脆不聽英文的模型，precision 會是 100%，但什麼都沒抓到 |

外加一個中文的存活檢查：指定幾個「一定要完整出現」的詞，以及你**實際看過**的錯聽（例如「椎間盤突出」被聽成「最艱難突出」）。英文再好，中文糊掉一樣扣分。

### 誠實說明這把尺的限制

`capture` 數的是**真實詞彙的型別數（word types）**，不是策展過的專業術語。字典的建法是「凡是在這些書裡出現過三次以上的字就收」，所以裡面也有一般英文字（腳本會用一張停用詞表擋掉最常見的那些）。

**它是一個幻覺偵測器 + 覆蓋率的代理指標，不是術語正確率。** 知道它量的是什麼，這個分數才有意義。這正是判讀診斷性研究的第一課：先確立你的 reference standard。

## 用法

```bash
pip install -r requirements.txt

# 1. 用你自己的語料建字典（純文字或 markdown 都可以）
python build_lexicon.py /path/to/your/corpus -o lexicon/mine.txt

# 2. 把每個模型 × 每組設定跑過你的音檔（一次一個模型，理由見下）
python transcribe_variants.py openai/whisper-large-v3          novad --clips clips/
python transcribe_variants.py MediaTek-Research/Breeze-ASR-25  novad --clips clips/

# 3. 評分
python eval_asr.py out/ --lexicon lexicon/mine.txt --domain domain.json
```

輸出長這樣：

```
model/variant                n  capture  garbage  precision   cjk✓   cjk✗
--------------------------------------------------------------------------
large-v3/novad              15      435      53      89.2%     8      2
breeze25/novad_nocond       15      649      44      93.7%     8      0

most-invented garbage per combo (this is where the hallucinations show):
  large-v3/novad            ['motibra', 'grutius', 'idioma', ...]
```

**一次只跑一個模型，這是刻意的。** 把兩個模型載進同一個 process，是這個專案第一個錯誤結論的來源：它們在一張 8GB 顯卡上互搶記憶體，於是第二個模型看起來「慢了兩倍」。壞掉的是量測工具，不是模型。

## 附的範例字典

`lexicon/pmr-en.txt` 是我自己在用的那一份：**187,227 個小寫英文單字**，從我私人研讀用的上百本復健醫學（PMR）教科書自動抽出來的。

放進來只是當**範例**，讓你不用先準備語料就能跑跑看，也讓復健科的同行可以直接用。

它是一份**去重、無序、無詞頻、無上下文**的單字清單，回推不出任何原文，本身不含任何來源書籍的表達性內容。原始語料不在這個 repo 裡，也不會提供。

**你自己的領域請用 `build_lexicon.py` 建自己的。** 一份復健科的字典拿去測心臟科的演講，是不對的尺。

## 我實測出來的結果

15 段醫學演講（6 段課堂 + 9 段案例討論），每段 8 分鐘：

| 設定 | 真實詞彙捕獲 | 精確度 | GPU 時間／每小時音訊 |
|---|---|---|---|
| Whisper large-v3（原本的預設） | 435 | 89.2% | 3.4 分鐘 |
| Breeze-ASR-25（純換模型） | 587 | 94.5% | 3.4 分鐘 |
| **Breeze-ASR-25 ＋ 設定調校** | **649** | 93.7% | **3.0 分鐘** |

[Breeze-ASR-25](https://huggingface.co/MediaTek-Research/Breeze-ASR-25) 是聯發科針對**台灣華語與中英夾雜**微調的開源模型（Apache 2.0）。醫學演講正好是中英夾雜的重災區。

### 負結果也是結果

- **兩個模型並用取聯集**：輸給單用 Breeze-ASR-25。
- **餵 hotwords / initial_prompt 提示術語**：兩個模型都變**更糟**。它會拿提示詞去發明新的錯字。`transcribe_variants.py` 裡保留了這些變體，你可以自己重現，不用相信我。
- **關掉 VAD**（語音活動偵測）：反而全面變好。VAD 在吃掉句子邊緣的真實語音。

### 還有一個教訓：不要只測一次

第一輪我只拿一段 10 分鐘的錄音試水溫（n=1），得到三個看起來很有道理的結論。擴大到 15 段、每個模型分開跑之後，**三個全部被推翻**：一個是量測工具壞掉（顯卡搶記憶體），一個是讓 LLM 自己挑證據造成的確認偏誤，一個是拿「文件沒寫」當「做不到」的缺席證據推論。

n=1 不是 benchmark。

## License

MIT. 作者 [陳柏威 Po-Wei Chen](https://drpwchen.com)（復健科醫師）。

如果這個工具幫你省下了時間，歡迎請我喝杯珍奶 🧡

[![Buy me a boba](https://img.shields.io/badge/BUY_ME_A_BOBA-F8E0BE?style=for-the-badge&labelColor=F8E0BE&color=F8E0BE)](https://drpwchen.bobaboba.me)

---

# asr-benchmark (English)

**Pick your ASR model with your own data, not someone else's leaderboard.**

A ruler for comparing ASR models and decoding settings on **your** recordings, with **no hand-corrected reference transcript required**.

📝 Full write-up (Traditional Chinese): [my-data-my-benchmark](https://drpwchen.com/posts/my-data-my-benchmark/)

## The idea

Build a lexicon from your field's literature, then ask one basic question of every word the model emits: **does this word exist in my field at all, or did the model invent it?** (`motibra`, `grutius`, `idioma` are real examples of what Whisper produced on medical lectures.)

That yields two numbers you must read together:

- **precision** — share of emitted latin word-types that are real words. Catches hallucination.
- **capture** — how many distinct real word-types it emitted at all. Catches the opposite failure: a model that just doesn't hear English scores 100% precision while capturing nothing.

Plus an optional CJK survival check for terms that must appear intact.

**Be honest about what this measures.** `capture` counts real *word-types*, not curated domain terminology, because the lexicon is "every word appearing in my field's books" (a short stoplist removes the most common ones). It is a hallucination detector and a coverage proxy, not a terminology accuracy score.

## Usage

```bash
pip install -r requirements.txt
python build_lexicon.py /path/to/corpus -o lexicon/mine.txt
python transcribe_variants.py MediaTek-Research/Breeze-ASR-25 novad --clips clips/
python eval_asr.py out/ --lexicon lexicon/mine.txt --domain domain.json
```

Run **one model per process**. Loading two models into one process on an 8 GB card made the second look "2x slower". The instrument was broken, not the model.

## Bundled example lexicon

`lexicon/pmr-en.txt`: 187,227 lowercase English words auto-extracted from 100+ physical-medicine-and-rehabilitation textbooks used for my own study. It is a deduplicated, unordered word list with no frequencies and no context; the source corpus is not included and is not distributed. Included as a runnable example. **Build your own for your own field.**

## Results on my data (15 medical lectures, 8 min each)

| Setup | Real word-types captured | Precision | GPU min / audio hour |
|---|---|---|---|
| Whisper large-v3 | 435 | 89.2% | 3.4 |
| Breeze-ASR-25 | 587 | 94.5% | 3.4 |
| **Breeze-ASR-25 + tuned** | **649** | 93.7% | **3.0** |

Negative results, so you don't repeat them: ensembling both models lost to Breeze alone; `hotwords` / `initial_prompt` made **both** models worse (they recycle the prompt into new wrong words); turning VAD **off** improved everything (it was eating real speech).

And: my first round was n=1, and produced three confident conclusions that were **all** later overturned. n=1 is not a benchmark.

MIT © 2026 [Po-Wei Chen](https://drpwchen.com), physiatrist.
