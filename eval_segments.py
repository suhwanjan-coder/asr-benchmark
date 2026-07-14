"""Ruler #2: segment granularity — the gate that decides whether a transcript is USABLE.

A model can transcribe every word correctly and still be useless. If it emits
30-second blocks, you can no longer say which sentence belongs to which slide,
which subtitle frame, or which moment in the recording.

This is not hypothetical. Breeze-ASR-26 (MediaTek's Taigi model) scores 2.0
segments/min with default decoding, versus 18-24 for Breeze-ASR-25 and Whisper
large-v3 — and its segment length is a flat 30.0s median, which is exactly the
Whisper decode window. It is not segmenting at all: fine-tuning degraded its
timestamp-token prediction, so it dumps one block per window.

That is fixable, and the fix is not in any model card: run the `novad_nocond_wts`
variant (word_timestamps=True). Word timings come from cross-attention alignment,
which never touches the timestamp tokens, and re-cutting on pauses restores
10+ segments/min at ~1.3x decode cost.

So: every candidate must clear BOTH gates. eval_asr.py (are the words real?) and
this one (can you locate them in time?).

Usage: python eval_segments.py out/
"""
import os
import re
import sys
import collections
import statistics

TS = re.compile(r'^\[(\d+):(\d+)\]')

# Slides change every 1-2 min, so >=10 segments/min aligns fine. The median gap
# guard catches a transcript that is nominally dense but clumped.
MIN_SEGS_PER_MIN = 10
MAX_MEDIAN_GAP_S = 8


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else 'out'
    agg = collections.defaultdict(lambda: {'segs': 0, 'clips': 0, 'gaps': [], 'minutes': 0.0})

    for f in sorted(os.listdir(d)):
        if not f.endswith('.txt'):
            continue
        parts = f[:-4].split('__')
        if len(parts) != 3:
            continue
        _, model, variant = parts
        ts = []
        with open(os.path.join(d, f), encoding='utf-8') as fh:
            for line in fh:
                m = TS.match(line)
                if m:
                    ts.append(int(m.group(1)) * 60 + int(m.group(2)))
        if len(ts) < 2:
            continue
        a = agg[f'{model}/{variant}']
        a['segs'] += len(ts)
        a['clips'] += 1
        a['minutes'] += (max(ts) - min(ts)) / 60 or 8
        a['gaps'] += [b - x for x, b in zip(ts, ts[1:]) if b >= x]

    if not agg:
        print(f'no timestamped transcripts found in {d}/')
        return

    print(f'{"model/variant":28} {"segs/min":>9} {"median gap":>11} {"max gap":>8}  verdict')
    print('-' * 76)
    for k in sorted(agg):
        a = agg[k]
        if not a['gaps']:
            continue
        spm = a['segs'] / max(a['minutes'], 1)
        med = statistics.median(a['gaps'])
        mx = max(a['gaps'])
        # A large MAX gap is not a defect: it is silence in the recording. Judge on
        # segs/min + median gap only.
        if spm >= MIN_SEGS_PER_MIN and med <= MAX_MEDIAN_GAP_S:
            verdict = 'OK'
        elif spm >= MIN_SEGS_PER_MIN / 2:
            verdict = 'COARSE - risky for alignment'
        else:
            verdict = 'FAIL - cannot align'
        print(f'{k:28} {spm:>9.1f} {med:>10.0f}s {mx:>7.0f}s  {verdict}')

    print(f'\ngate: >={MIN_SEGS_PER_MIN} segs/min AND median gap <={MAX_MEDIAN_GAP_S}s')
    print('a FAIL with a ~30s median segment length means the model is not predicting')
    print('boundaries at all -> retry with the novad_nocond_wts variant before ruling it out.')


if __name__ == '__main__':
    main()
