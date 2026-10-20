# 講座筆記轉錄引擎：CPU Whisper medium 對 Breeze-ASR-25（2026-10-20／21 實測）

## 結論

**換。** 四場中文講座、40 個盲判窗口，Breeze-ASR-25 的字元錯誤率（CER）是 0.090，Whisper medium 是 0.131（兩位評審平均），Breeze 在 29 個窗口勝出、medium 10 個、平手 1 個（符號檢定 p = 0.003）。差距主要來自 medium 整句漏掉（刪除率 6.6% 對 3.1%），不是口語贅字的取捨。代價是 CPU 時間：同一台機器、同樣 16 執行緒、int8，Breeze 是 medium 的 1.6 倍：乾淨計時下每小時音檔 medium 約 18 分鐘、Breeze 約 29 分鐘（第 6 節），尖峰記憶體多約 1 GB。這個代價對每場 30–115 分鐘、一天跑幾場的流水線可以接受；錯字少一成以上、漏句少一半，直接減少後面查核的修正量。

hotwords（字典提示，兩個引擎同一份 53 詞）：兩個引擎的盲判 CER 都變差、耗時 1.3–2 倍，不要用（第 7 節）。

## 1. 這次怎麼測

| 項目 | 做法 |
|---|---|
| 機器 | ACHIH-MAIN，Intel Core Ultra X7 358H（16 核）、31.6 GB RAM、無 NVIDIA GPU |
| 引擎 | `Systran/faster-whisper-medium`（HF 快取複製到 `models/whisper-medium-ct2`）；`SoybeanMilk/faster-whisper-Breeze-ASR-25`（CTranslate2 版，2.9 GB，下載到 `models/breeze-asr-25-ct2`） |
| 解碼設定 | 兩個引擎完全相同：`novad_nocond`（beam 5、VAD 關、不依賴前文）、language=zh、int8、cpu_threads=16。這和 lecture-to-notes 正式轉錄的設定一致（VAD 關是該專案 2026-07-12 起的預設） |
| 執行方式 | 一次只載入一個模型、一個程序跑完退出再換下一個（README 的教訓），全程不與其他重 CPU 工作並行；`bench_run.py` 記 wall time、CPU 秒數、尖峰 RSS |
| 音檔 | 全部 16 kHz 單聲道 wav，ffmpeg 自原始錄影／錄音抽出，原檔未動 |
| 評分 | `score_bench.py`（全場）＋ `make_windows.py` / `score_silver.py`（盲判窗口），可重跑 |

### 四場講座

| 代號 | 講座 | 錄音型態 | 長度 | 參考資料 |
|---|---|---|---|---|
| idsa-hu | 胡婉妍（臺大感染科）加強型流感疫苗，IDSA 論壇 2026-10-04 | Zoom 錄影 | 30.6 分 | Groq large-v3-turbo 逐字稿、人工查核後筆記、投影片 OCR |
| idsa-huang | 黃立民（臺大小兒感染科）疫苗學新時代，同論壇 | Zoom 錄影 | 40.3 分 | 人工查核後筆記、投影片 OCR（Groq 當時 loop 失敗，無） |
| emha-feng | 馮嬿臻（臺大公衛）生物與基因因子與人口健康，EMHA 2026-10-17 | 教室手機錄音 | 前 60 分（全長 79 分） | Groq 逐字稿、課堂版講義導讀 |
| emha-hung | 洪冠予（新竹臺大分院）品質指標應用與疾病別認證，EMHA 2026-10-17 | 教室手機錄音 | 前 60 分（全長 102 分） | Groq 逐字稿、課堂版講義導讀 |

為什麼不是交辦單上說的 D:\lectures 四場：那 12 支已做完筆記的影片在 2026-10-16 已依阿志決定移出 OneDrive 並清空資源回收筒，D:\lectures 只剩 IDSA 兩支 mp4；全機搜尋後拿 G: 上 EMHA 10/17 的兩段課堂錄音補足，長度超過 60 分的只取前 60 分。這讓樣本多了「教室手機錄音」這個條件，比四場都是 Zoom 更接近真實用途。

## 2. 參考答案是什麼（沒有人工逐字稿，要先講清楚）

這四場都沒有人聽打的逐字稿。三層參考，各自回答不同問題：

1. **盲判參考稿（silver reference）**：每場隨機抽 10 個 60 秒窗口（固定種子 20261020，跳過開頭 90 秒），把 medium、Breeze、Groq（有的話）的文字打亂標籤成 A/B/C，加上該時刻投影片 OCR 與術語表，交給兩位互不相見的 Sonnet 評審逐句仲裁出「講者最可能說的話」。評審看不到標籤對應，也拿不到音檔。兩位評審彼此的 CER 是 0.015–0.028，參考稿本身穩定。這是本報告的主指標。
2. **Groq large-v3-turbo 全場逐字稿**（第三個引擎，三場有）：拿來算全場 CER，意義是「與第三個引擎的差異」，不是正確率。
3. **人工查核後筆記裡的術語**：字典術語（見第 3 節）在筆記本文出現、且至少一份逐字稿寫出來的，看引擎有沒有逐字寫對。

盲判法的已知偏誤：評審是文字層仲裁，候選都聽錯的字評審也救不回來；較長、較通順的候選有被偏好的風險。為此另外做了兩個檢查：(a) 去掉口語贅字（那、就是、然後……）後再算一次 CER，結果幾乎不變；(b) 抽 medium 刪除最多的窗口（idsa-hu#06）人工比對三家文字，medium 漏掉的整句「它中間的這個差異就是所謂的 seroconversion difference」在 Breeze 和 Groq 兩家都有，是真漏不是 Breeze 幻覺。

## 3. 字典與 hotwords（兩個引擎同一份）

`build_terms.py` 從 idea-lab 的 02-Clinical、06-EMHA、03-Research、00-Inbox 共 1,648 張卡片建出（排除本次受測的兩份 IDSA 筆記；EMHA 兩份課堂版筆記不在 vault 內，天然排除）：

| 產物 | 規則 | 數量 |
|---|---|---|
| `lexicon/idealab-en.txt` | 英文詞型，全語料出現 ≥ 3 次（同 build_lexicon.py） | 13,615 |
| `lexicon/idealab-zh.txt` | 筆記縮寫表的中文欄（299 條）＋ jieba 斷詞 ≥ 3 字、文件頻率 5 至 25% 之間 | 1,115 |
| `lexicon/hotwords.txt` | 縮寫表中文名、縮寫、英文全名詞各取最高文件頻率者，裁到 Whisper 提示上限內（198 tokens） | 53 個詞 |

中文術語表仍混有一般詞（一小部分、值得注意），術語命中率的絕對值因此偏鬆；兩個引擎用同一份，相對比較不受影響。

## 4. 結果：盲判 CER（主指標）

兩位評審平均；sub／del／ins 是替換、刪除、插入各占參考字元數的比例。

| 講座 | 引擎 | CER | 替換 | 刪除 | 插入 | 去贅字 CER | 窗口勝負（評審 1／評審 2，medium：Breeze：平） |
|---|---|---|---|---|---|---|---|
| idsa-hu | medium | 0.120 | 0.033 | 0.076 | 0.011 | 0.112 | 3:7:0／4:6:0 |
| idsa-hu | **Breeze** | **0.093** | 0.039 | 0.028 | 0.026 | 0.086 | |
| idsa-hu | Groq turbo | 0.131 | 0.035 | 0.076 | 0.020 | 0.117 | |
| idsa-huang | medium | 0.179 | 0.065 | 0.098 | 0.015 | 0.183 | 2:8:0／3:7:0 |
| idsa-huang | **Breeze** | **0.110** | 0.044 | 0.035 | 0.031 | 0.115 | |
| emha-feng | medium | 0.123 | 0.058 | 0.053 | 0.013 | 0.120 | 2:7:1／1:9:0 |
| emha-feng | **Breeze** | **0.089** | 0.038 | 0.038 | 0.014 | 0.085 | |
| emha-feng | Groq turbo | 0.117 | 0.064 | 0.032 | 0.022 | 0.125 | |
| emha-hung | medium | 0.103 | 0.051 | 0.040 | 0.011 | 0.105 | 3:7:0／2:7:1 |
| emha-hung | **Breeze** | **0.065** | 0.035 | 0.022 | 0.008 | 0.065 | |
| emha-hung | Groq turbo | 0.129 | 0.057 | 0.064 | 0.008 | 0.131 | |
| **四場合計（40 窗口）** | medium | 0.131 | 0.052 | 0.066 | 0.013 | 0.130 | 10:29:1（p = 0.003） |
| | **Breeze** | **0.090** | 0.039 | 0.031 | 0.019 | 0.088 | |
| | Groq turbo（30 窗口） | 0.125 | 0.053 | 0.055 | 0.017 | 0.124 | |

讀法：
- Breeze 每場都贏，Zoom 錄影與教室手機錄音都一樣；差距最大的是黃立民（medium CER 0.18，講者語速快、英文術語多）。
- medium 的錯誤有一半是刪除（0.066），Breeze 的刪除只有 0.031；替換率兩者差不到 1.5 個百分點。medium 漏句是本次最主要的發現。
- Groq large-v3-turbo（現行的外部稽核引擎）在這四場比 medium 好不了多少，刪除率同樣高。
- 兩位評審的結論一致（每場勝負方向相同），合併 40 窗口的符號檢定 p = 0.003。2026-10-12 那次 4×8 分鐘的結果是 p = 0.63，這次差異清楚得多：樣本從 32 分鐘加到 191 分鐘，而且參考稿由盲判產生，不再只靠英文字典尺。

## 5. 結果：全場指標（字典尺、術語命中、與 Groq 的差異）

| 講座 | 引擎 | 對 Groq CER | 兩引擎互相 CER | 術語命中（n） | 英文真實詞型 | 垃圾詞 | 英文精確度 | 迴圈段 |
|---|---|---|---|---|---|---|---|---|
| idsa-hu | medium | 0.173 | 0.160 | 82.4%（34） | 39 | 10 | 79.6% | 0 |
| idsa-hu | Breeze | 0.162 | | 79.4%（34） | 56 | 11 | 83.6% | 0 |
| idsa-huang | medium | — | 0.185 | 90.9%（33） | 23 | 6 | 79.3% | 0 |
| idsa-huang | Breeze | — | | 93.9%（33） | 39 | 10 | 79.6% | 1* |
| emha-feng | medium | 0.133 | 0.128 | 96.7%（30） | 185 | 56 | 76.8% | 1 |
| emha-feng | Breeze | 0.129 | | 90.0%（30） | 219 | 50 | 81.4% | 0 |
| emha-hung | medium | 0.116 | 0.108 | 96.9%（32） | 64 | 17 | 79.0% | 0 |
| emha-hung | Breeze | 0.119 | | 96.9%（32） | 91 | 15 | 85.8% | 0 |

\* 「b c 細胞」同一短語連說三次，不是幻覺迴圈。

- 英文真實詞型：Breeze 四場都多（+17、+16、+34、+27），精確度三場高 4–7 個百分點、一場持平（黃立民 +0.3），與 README 作者在復健科資料上的方向一致。上次 8 分鐘片段測出的「字典尺沒有解析力」在全場 30–60 分鐘後解析力回來了。
- 術語命中率兩者接近（差在 ±7 個百分點內、n 30–34；術語集是「筆記出現且任一份逐字稿寫出」的交集，含 hotwords 版本，所以 n 比只算基準時略大），這個指標在中文講座解析力低，不當決策依據。
- 兩引擎互相 CER 0.11–0.19：兩者差異的大小，正好與盲判量到的錯誤率同量級，表示兩者錯的地方多半不重疊。

## 6. 耗時與資源

同一台機器、16 執行緒、int8；wall time 只算轉錄，不含載入模型（medium 3–4 秒、Breeze 8 秒）。

| 講座 | 音檔分鐘 | medium 分鐘（RTF） | Breeze 分鐘（RTF） | Breeze／medium | medium 尖峰 RSS | Breeze 尖峰 RSS |
|---|---|---|---|---|---|---|
| idsa-hu | 30.6 | 14.3（0.47） | 15.9（0.52） | 1.11 | 2.1 GB | 3.0 GB |
| idsa-huang | 40.3 | 20.5（0.51） | 26.8（0.67） | 1.31 | 3.0 GB | 4.5 GB |
| emha-feng | 60.0 | 26.4（0.44） | 41.9（0.70） | 1.59 | 3.8 GB | 4.4 GB |
| emha-hung | 60.0 | 20.8（0.35） | 34.6（0.58） | 1.66 | 3.9 GB | 4.8 GB |

計時干擾說明：idsa-hu 與 idsa-huang 的 medium 跑的時候，字典建置（jieba，單核）同時在跑，兩個 Breeze 也有部分重疊，所以 IDSA 兩場的比值偏小；EMHA 兩場無其他負載，比值 1.6 較可信。乾淨重測（兩個引擎各跑一次 idsa-hu，機器無其他負載，03:00 跑）：

| 引擎 | 音檔分鐘 | wall 分鐘 | RTF | 尖峰 RSS | 段數 |
|---|---|---|---|---|---|
| medium | 30.6 | 9.3 | 0.30 | 1.8 GB | 590（與第一趟相同） |
| Breeze | 30.6 | 14.8 | 0.48 | 3.0 GB | 453（第一趟 437，int8 多執行緒下不完全可重現） |

比值 1.59，與 EMHA 兩場的 1.6 一致。換算：每小時音檔 medium 約 18 分鐘、Breeze 約 29 分鐘；一場 115 分鐘講座約 35 分鐘對 56 分鐘。

每分鐘段數：medium 19–29、Breeze 14–21。Breeze 的段比較長，lecture-to-notes 的投影片對齊靠段落時間戳，段落變長對齊粒度稍差，但 14 段／分鐘仍是每 4 秒一段，足夠。

Breeze 直接輸出繁體（medium 這次也輸出繁體，但 lecture-to-notes 正式跑過的 medium 逐字稿多為簡體，需 s2t 轉換）；Breeze 會在數字與英文前後加空格。

## 7. hotwords（字典提示）

兩個引擎各用 `lexicon/hotwords.txt`（53 個詞，縮寫表的中文名、縮寫、英文全名詞）跑 `novad_nocond_hot`，其餘設定不變。medium 第一場就明顯變差，所以只跑兩場（一 Zoom、一教室錄音）× 兩引擎，省下的機器時間拿去做乾淨計時。盲判 CER 用同一組窗口與同兩位評審的參考稿重算（參考稿是由基準候選仲裁出來的，對 hotwords 版本略為不利，解讀時要打折）。

| 講座 | 引擎 | 盲判 CER 基準 → hotwords | 對 Groq CER 基準 → hotwords | 英文精確度 基準 → hotwords | 迴圈段 | wall 分鐘 基準 → hotwords |
|---|---|---|---|---|---|---|
| idsa-hu | medium | 0.120 → 0.186 | 0.173 → 0.265 | 79.6% → 74.6% | 0 → 7 | 14.3 → 29.2 |
| idsa-hu | Breeze | 0.093 → 0.101 | 0.162 → 0.160 | 83.6% → 87.9% | 0 → 1 | 15.9 → 27.3 |
| emha-hung | medium | 0.103 → 0.192 | 0.116 → 0.153 | 79.0% → 75.0% | 0 → 1 | 20.8 → 40.6 |
| emha-hung | Breeze | 0.065 → 0.102 | 0.119 → 0.119 | 85.8% → 84.9% | 0 → 0 | 34.6 → 45.5 |

medium 加 hotwords 後錯誤率近乎翻倍、出現重複迴圈，而且因為每個 30 秒解碼窗都多了 198 個提示 token，耗時加倍。Breeze 加 hotwords 後對 Groq 的差異不變、英文精確度一場升一場降、盲判 CER 略差，耗時多 1.3–1.7 倍。兩邊都不值得。這與 README 作者的負結果、以及 lecture-to-notes 記憶中 initial_prompt 的負結果方向一致：提示詞不會讓模型「聽懂」，只會讓它把聽不清的音拼成提示裡的字。

## 8. 建議與代價

**建議：lecture-to-notes 的 CPU 主轉錄改用 Breeze-ASR-25，Groq 稽核維持現狀。**

切換不需要改程式，lecture-to-notes 已內建別名：
1. `config.yaml` 的 `paths.whisper_model_dir` 填 `C:/Users/suhwa/dev/asr-benchmark/models`（別名 `breeze25` 會展開成該資料夾下的 `breeze-asr-25-ct2`，資料夾名已對上）。
2. `run_lecture.py` 加 `--whisper-model breeze25`（預設是 medium）。
3. 先用一場已有筆記的講座走完整流程（prepare → tier → render → finish）確認投影片對齊與 asr_suspects 正常，再改預設。

代價與風險：
- CPU 時間：1.6 倍，每小時音檔多約 11 分鐘；一場 115 分鐘講座的轉錄從約 35 分鐘變成約 56 分鐘。可以接受，因為轉錄是背景工作，查核才是人力瓶頸。
- 記憶體：尖峰多約 1 GB（4.4–4.8 GB），這台 31.6 GB 無壓力；舊機（LAPTOP-4Q87TNH8）若也要跑要先確認。
- 插入率略高（0.019 對 0.013）：Breeze 偶爾把聽不清的英文寫成相近英文字（email 代替 疫苗、self-conversion 代替 seroconversion），這類錯誤查核時用投影片可辨認；medium 的錯誤型態是整句消失，查核者看不到就補不回來，後者更危險。
- 模型來源是第三方轉檔（SoybeanMilk），非聯發科官方 CTranslate2 版；本次用的檔案已留在 `models/`（git 忽略），換機要重新下載 2.9 GB。
- 2026-10-12 記憶檔的「維持 medium」結論由本報告取代。

## 9. 限制

- 沒有人工聽打的逐字稿；主指標是盲判參考稿，評審沒聽音檔。候選三家都錯的字不會被算成錯。
- n = 4 場、40 窗口；四場都是國語為主的醫學／公衛講座，英文演講（如 Ustianowski 那場）未測。
- 字典的中文術語含一般詞，術語命中率只能看相對值；英文字典有 120 個字母重複兩次的壞詞（如 aabbddoommiinnaall，來自 vault 某些檔的重複字元），占 13,615 的 0.9%，只會讓垃圾詞略少算，不影響方向。
- EMHA 兩場只取前 60 分鐘。
- 第一輪計時受字典建置干擾（第 6 節），以乾淨重測與 EMHA 兩場為準。

## 10. 檔案

- 腳本（repo 根目錄，commit SHA 見末行）：`bench_run.py`、`build_terms.py`、`score_bench.py`、`make_windows.py`、`score_silver.py`
- 字典：`lexicon/idealab-en.txt`、`lexicon/idealab-zh.txt`、`lexicon/hotwords.txt`、`lexicon/terms_meta.json`
- 實跑產物（`_bench/`，git 忽略，留在本機）：`audio/`（4 wav）、`out/`（逐字稿 JSON／txt、`timings.jsonl`）、`out_timing/`（乾淨計時）、`ref/`（Groq 稿、筆記、投影片 JSON）、`silver/` 與 `silver_hot/`（分窗包、key、兩位評審的參考稿）、`scores.json`、`scores_silver_j1.json`、`scores_silver_j2.json`、`scores_silver_hot_j1.json`、`scores_silver_hot_j2.json`、`logs/`
- 重跑：

```
.venv\Scripts\python.exe bench_run.py models\whisper-medium-ct2 novad_nocond --tag medium --audio _bench\audio\idsa-hu.wav --out _bench\out --threads 16
.venv\Scripts\python.exe bench_run.py models\breeze-asr-25-ct2 novad_nocond --tag breeze25 --audio _bench\audio\idsa-hu.wav --out _bench\out --threads 16
.venv\Scripts\python.exe score_bench.py --clips idsa-hu idsa-huang emha-feng emha-hung
.venv\Scripts\python.exe make_windows.py --clips idsa-hu idsa-huang emha-feng emha-hung --k 10
.venv\Scripts\python.exe score_silver.py --clips idsa-hu idsa-huang emha-feng emha-hung --judge _j1
```

## 11. 自主決定紀錄

- 影片已刪，改用 G: 的 EMHA 課堂錄音補兩場並截前 60 分鐘，沒有回頭問。
- 參考答案採盲判 silver（兩位 Sonnet 評審）而非只靠英文字典尺；派了 8 個 Sonnet 評審工人，每人只看自己那一場的 packet。
- faster-whisper 1.2.1 與 PyAV 19 不相容（`metadata_errors` 參數），venv 內把 av 降到 15.1.0（與 lecture-to-notes 的 venv 同版）。
- medium 用 HF 快取的本機副本（HF hub 下載 API 與新版 huggingface_hub 不合）。
- 字典建置第一版用 jieba 詞性標註，跑了 55 分鐘仍未完且拖慢計時，改成不帶 HMM 的斷詞（45 秒）；中文詞改取 3 字以上。
- Groq 金鑰檢查指令被權限擋下，沒有為黃立民補做 Groq 稿，該場只用盲判與筆記術語。
- hotwords 第一場（medium）結果已明顯變差，把原排的 4 場 × 2 引擎縮成 2 場 × 2 引擎，省下約 1.5 小時機器時間給乾淨計時。

---
本報告與五支腳本的 commit：db0d9efa35d036993f880493c26223cc8db4b59c（2026-10-21 03:10，分支 main）。
