# Changelog

## [0.2.1] - 2026-07-15

Correcting how v0.2.0 read its own breeze26 number.

### Changed
- ==**The "182 vs 649" result was misread, and the README/RESULTS now say so.**== Breeze-ASR-26
  is designed to emit Han characters, and it does that to English too — it **transliterates**
  medical terms (`interlamina` → 印特拉蜜拉, `facet` → 防震). Its output volume did not
  collapse; it has the **most** Han characters of the three models tested (19,617 vs
  breeze25's 18,514). Only its English collapsed (313 tokens vs 1,293).
- So `capture=182` conflates *missed* terms with *transliterated* terms. The conclusion for
  this use case is unchanged (a note needs `interlamina`, not 印特拉蜜拉), but the reason is
  different: **it is not "deaf to English terms", it renders them in Han characters.**
- **New documented blind spot:** an English-only lexicon **systematically underrates any model
  that prefers Han output**. README now states which question the ruler answers ("did it write
  it the way I need?") and which it cannot ("did it understand?").
- Credit where due: **Breeze-ASR-26 beats Google Gemini 3 Flash on its own turf** (Taigi CER
  30.13 vs 32.52), plus Yating (32.11) and the MOE Taigi input method (30.70). v0.2.0 failed
  to mention this; the Taigi result stands and nothing here disputes it.

### Fixed
- ==**The hotwords negative-result numbers did not reproduce.**== RESULTS.md claimed
  breeze25+hotwords = 493 capture / 26 garbage ("−16%"); re-running `eval_asr.py` against the
  transcripts gives **580 / 36 / 91.6%**. Corrected, and the claim restated: vocabulary
  injection does not *destroy* capture, it simply **buys none** (587→580) while adding garbage
  (29→36) and costing precision. The conclusion ("don't use hotwords") is unchanged; the
  evidence for it is now the *absence of the promised benefit* plus the new invented words
  (`sacroilar`, `buteroli`, `paravertibone` — none of which appear in un-prompted runs).

## [0.2.0] - 2026-07-14

The second ruler, and what it found.

### Added
- **`eval_segments.py` — ruler #2: segment granularity.** A model can transcribe every word
  correctly and still be unusable if it emits 30-second blocks. Gate: >=10 segments/min with
  a median gap <=8s. Every candidate must now clear **both** gates.
- **`novad_nocond_wts` variant** in `transcribe_variants.py` — word-level timestamps
  (cross-attention alignment) plus pause-based re-segmentation. This is the fix for models
  whose timestamp-token prediction was degraded by fine-tuning.
- **`RESULTS.md`** — the full worked example on a real corpus: every table, every negative
  result, and every limitation, including what was *not* tested.

### Findings
- **Breeze-ASR-26 on Mandarin/English medical lectures: capture 182 vs Breeze-ASR-25's 649**
  (n=15) — under a third. Its garbage count is low (8) only because it barely emits English
  terms at all, which is what a Taigi-tuned model should do. This, not segmentation, is the
  real reason not to use it outside Taigi.
- **Breeze-ASR-26's segmentation is broken with default decoding** (1.8–2.2 segs/min; a flat
  30.0s median = the Whisper decode window, i.e. it is not predicting boundaries at all),
  while Breeze-ASR-25 scores 18.2 and Whisper large-v3 scores 24.4. Not documented upstream:
  ASR-25's model card advertises "enhanced time alignment, suitable for automatic
  captioning"; ASR-26's card does not mention timestamps at all.
- **It is fixable.** `word_timestamps=True` bypasses the timestamp tokens entirely and
  restores 10.0–10.7 segs/min (n=4) at ~1.29x decode time. **If you use Breeze-ASR-26 for
  Taigi subtitles or any timestamp-dependent job, pass `word_timestamps=True`.**
- Scope: measured on Mandarin/code-switched audio. **No Taigi audio was tested** — the
  degradation lives in the weights and very likely reproduces there, but that is an
  inference, not a measurement.

### Note
An earlier internal verdict ("Breeze-ASR-26 cannot align to timestamps, do not use it") was
**wrong** and is retracted here. The defect was our decode configuration, not the model.
Rulers tell you a score is failing; they do not tell you whose fault it is.

## [0.1.0] - 2026-07-13

Initial public release.

### Added
- `build_lexicon.py` — build a domain word-list from your own corpus (text or markdown).
- `eval_asr.py` — ruler #1: score capture (real word-types) and precision (hallucination
  rate) against that lexicon, with no ground-truth transcript required.
- `transcribe_variants.py` — run a model × settings matrix, one model per process.
- `lexicon/pmr-en.txt` — 187,227-word example lexicon from 100+ rehabilitation textbooks.
