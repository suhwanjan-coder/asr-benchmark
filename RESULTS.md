# Results on one real corpus — a worked example of using this ruler

This is what the output of this repo looks like when you point it at a real problem.
It is included as an **example**, not as a recommendation: my corpus is Mandarin/English
code-switched physical-medicine-and-rehabilitation lectures. If yours is anything else,
build your own lexicon and run your own matrix — that is the entire point of the repo.

Narrative version, with the reasoning: <https://drpwchen.com/posts/my-data-my-benchmark/>

## Corpus

| | |
|---|---|
| clips | 15 × 8 min (6 didactic lectures + 9 case discussions), Mandarin with English medical terms |
| English subset | 6 clips (American / Hong Kong / Japanese speakers) |
| granularity re-test | 4 clips |
| lexicon | 187,227 English word-types from 100+ PMR textbooks (`lexicon/pmr-en.txt`, bundled) |
| hardware | RTX 3070 Ti, 8 GB |

## What the official benchmarks already told me

MediaTek publishes WER for Breeze-ASR-25 vs Whisper-large-v2 (lower is better):
CSZS-zh-en **13.01 vs 29.49**, ASCEND-MIX **16.38 vs 21.01**, CommonVoice16-zh-TW
**7.97 vs 9.84**. So "is Breeze-ASR-25 better than Whisper at Taiwanese Mandarin
code-switching" was **already answered** — I did not need to re-prove it.

**Breeze-ASR-26's model card, by contrast, publishes exactly one number: a Taigi CER of
30.13%.** No Mandarin benchmark. No English benchmark. No code-switching benchmark. No
timestamp or alignment data of any kind. Outside Taigi, its behaviour is simply undocumented
— even though it is a sibling fine-tune of the same Whisper base as ASR-25. Is it "ASR-25
plus Taigi", or did Taigi cost it something? Nobody had published an answer.

That gap is what this repo was pointed at. Three questions official benchmarks could not
answer:

1. Does Breeze-ASR-25's advantage carry over to **my domain vocabulary**? (ASCEND and
   CommonVoice are everyday speech, not lectures full of `nucleus pulposus` and
   `spondylolisthesis`.)
2. Are the **timestamps** usable for aligning a transcript to slides? (Neither card says.)
3. **What does the Taigi model do outside Taigi?** (Undocumented, so: measure it.)

All three mattered, and the last two produced findings that are in no model card.

## Ruler #1 — term quality (`eval_asr.py`)

| model / variant | capture (real word-types) | garbage | precision | GPU min / audio hr |
|---|---|---|---|---|
| large-v3 / base (old default) | 435 | 51 | 89.2% | 3.4 |
| breeze25 / base | 587 | 29 | 94.5% | 3.4 |
| **breeze25 / novad_nocond (adopted)** | **649** | 37 | 93.7% | **3.0** |
| breeze25 / novad_b10 | 604 | **21** | **96.4%** | 5.1 |
| breeze26 / novad_nocond (Taigi model, for reference) | 182 | 8 | 81.6% | 3.0 |

**+49% real medical terms over the old default, and faster.** The official advantage does
extend to domain vocabulary. `beam10` buys precision at 1.7x the time and loses recall —
not worth it.

The last row is the Taigi model, included only to answer the obvious question. On
Mandarin/English medical lectures it captures **182 real terms vs breeze25's 649** — under
a third. Its garbage count is low (8) simply because it barely emits English terms at all,
which is exactly what you would expect from a Taigi-tuned model. **That row is not a verdict
on Breeze-ASR-26; it is a boundary marker — do not use it outside its language.**

### Settings mattered almost as much as the model

- **VAD off.** The voice-activity filter was silently eating quiet speech at segment edges
  (pauses, breaths, page turns). Turning it off is nearly free: more real terms, *fewer*
  invented ones, and it does **not** reintroduce silence hallucination or repetition loops
  (0 of each across 2,236 lines).
- **`condition_on_previous_text` off.** Feeding the previous segment back as context
  propagates a mishearing forward; at worst the decode locks into a repeating loop.

### Negative results (reproduce them yourself with the bundled variants)

| setup | capture | garbage | precision |
|---|---|---|---|
| **breeze25 (no prompt)** | **587** | 29 | **94.5%** |
| breeze25 + hotwords | 493 | 26 | 91.7% |
| large-v3 (no prompt) | 435 | 51 | 89.2% |
| large-v3 + hotwords | 446 | 56 | 88.2% |

**Vocabulary injection HURTS.** Both `hotwords` and `initial_prompt` lower capture and
invent *new* garbage (`paravertibone`, `sacroilar`, `buteroli`) by dragging what the model
heard toward the terms you supplied. A prompt is a **pull, not a dictionary**. The two
terms I most wanted rescued (`nucleus pulposus`, `prolotherapy`) stayed wrong even when
spelled out verbatim in the prompt.

**Two-model ensembling LOST**: union of large-v3 + breeze25 captured *fewer* real terms
(571 vs 587) with **5x the garbage** (147 vs 29) at 2x the GPU time. A union inherits the
weaker model's hallucinations. Deleted.

**English is a tie**: 1535 vs 1537 word-types (breeze25 vs large-v3), precision 98.6% vs
97.8%, and breeze25 hallucinated zero Chinese characters into English audio. So one model
covers everything — no language routing needed at the term level.

## Ruler #2 — segment granularity (`eval_segments.py`)

This is the gate most people skip, and it is the one that produced the novel finding.

Breeze-ASR-25's model card advertises *"Enhanced time alignment, suitable for automatic
captioning."* **Breeze-ASR-26's model card does not mention timestamps, alignment or
captioning at all.** Measured, that silence turns out to be meaningful:

| model (default decoding) | segs/min | median segment length | slide alignment |
|---|---|---|---|
| large-v3 | 24.4 | ~2 s | OK |
| breeze25 | 18.2 | ~2 s | OK |
| **breeze26** | **1.8 – 2.2** | **30.0 s** | **FAIL** |

A **flat 30.0-second median is the Whisper decode window.** Breeze-ASR-26 is not
segmenting at all — fine-tuning on synthetic Taigi degraded its timestamp-token
prediction, so it emits one block per window. On one 10-minute clip (a single example,
not the corpus average): breeze25 produced 253 segments, breeze26 produced 20.

### The fix (n=4 clips)

Whisper can produce timings a second way: **word-level timestamps via cross-attention
alignment**, which never touches the timestamp tokens.

| breeze26 | segs/min | passes gate (>=10)? |
|---|---|---|
| default decoding | 1.8 – 2.2 | no (0 of 4 clips) |
| **`novad_nocond_wts` + re-segmentation** | **10.0 – 10.7** | 3 of 4 clips |

Word timings come back healthy: monotonic, ~100% audio coverage, 1-4% zero-length words.
Cost: **1.29x decode time**.

> **If you use Breeze-ASR-26 for anything timestamp-dependent — Taigi subtitles, transcript
> alignment, clip location — pass `word_timestamps=True`. With default decoding its
> segmentation is unusable.** This is not documented anywhere upstream.

**"breeze26 cannot do timestamps" would have been a wrong conclusion**, and it was ours for
two days. The default decode config was the defect, not the model.

## Limits of these results

- **No Taigi audio was tested.** Zero Taigi clips exist in this corpus. Breeze-ASR-26's
  published CER of 30.13% is MediaTek's number, not mine. I am neither endorsing nor
  disputing its actual Taigi quality.
- **The granularity finding is measured on Mandarin audio, not Taigi.** The timestamp-token
  degradation lives in the weights, so it very likely reproduces on Taigi — but that is an
  inference, not a measurement.
- **`capture` counts real word-types, not curated terminology.** It is a hallucination
  detector plus a coverage proxy. See the README's honesty section.
- **My ruler is not your ruler.** If you care about latency, punctuation, diarisation or
  emotion, you need a different one.

## The discipline these numbers depend on

My first round was **n=1** and produced three confident conclusions that were *all* later
overturned:

| n=1 conclusion | what it actually was |
|---|---|
| "Breeze is 2x slower" | **instrument error** — two models loaded in one process, fighting over 8 GB of VRAM. Separated, they are the same speed. |
| "Breeze wins English terms 9:1" | **confirmation bias** — an LLM picked the examples. Programmatic counting over the full set: 2-3:1. |
| "The Taigi model can't do Mandarin" | **argument from absence** — inferred from the model card not listing a Mandarin score. Measured, it ties on one clip (and loses on lectures). |

Hence the three rules baked into this repo: **n >= 3, one model per process, and scoring
done by a script rather than by a model.**

And one more, learned while producing the breeze26 row above: **a scoring script is an
instrument too, and it can lie.** Our internal runner derived the model's label with
`'breeze25' if 'breeze' in path else 'large-v3'` — so breeze26's output was silently
labelled breeze25, collided with existing files, and was skipped. That single line is why
breeze26 had never been scored on the full corpus at all. The score you never see is more
dangerous than the score that is wrong.

MIT © 2026 [Po-Wei Chen](https://drpwchen.com)
