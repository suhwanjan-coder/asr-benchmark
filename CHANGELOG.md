# Changelog

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
