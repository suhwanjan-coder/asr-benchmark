"""Cut K random 60 s windows per clip and build BLIND adjudication packets.

For every window the packet holds the candidate transcripts under shuffled labels
(A/B/C), the slide OCR text on screen at that time (when a slides JSON exists) and a
short glossary (dictionary terms found in the human-verified note). A judge that
never sees the label key writes the most plausible verbatim transcript of the
window ("silver reference"); score_silver.py then scores every engine against it.

Outputs: <silver_dir>/<clip>__packet.json  (for the judge)
         <silver_dir>/key.json              (label -> engine per window; keep away from judges)

Usage:
    python make_windows.py --clips idsa-hu idsa-huang emha-feng emha-hung --k 10 --seed 20261020
"""
import argparse
import json
import os
import random

from score_bench import term_set


def window_text(segs, t0, t1):
    return ' '.join(s['text'] for s in segs if t0 <= s['start'] < t1).strip()


def slide_text(slides, t):
    for s in slides:
        if s['timestamp_start'] <= t < s['timestamp_end'] + 1:
            q = s.get('ocr', {}).get('quick_text') or ''
            # drop Zoom chrome lines, keep slide content
            lines = [l for l in q.splitlines() if len(l) > 3 and not l.startswith(('zoom', 'Admin', 'REC'))]
            return '\n'.join(lines)[:800]
    return ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='_bench/out')
    ap.add_argument('--ref', default='_bench/ref')
    ap.add_argument('--silver', default='_bench/silver')
    ap.add_argument('--clips', nargs='+', required=True)
    ap.add_argument('--variant', default='novad_nocond')
    ap.add_argument('--engines', nargs='+', default=['medium', 'breeze25', 'groq'])
    ap.add_argument('--k', type=int, default=10)
    ap.add_argument('--win', type=float, default=60.0)
    ap.add_argument('--skip-head', type=float, default=90.0)
    ap.add_argument('--seed', type=int, default=20261020)
    ap.add_argument('--lex-en', default='lexicon/idealab-en.txt')
    ap.add_argument('--lex-zh', default='lexicon/idealab-zh.txt')
    ap.add_argument('--reuse-key', help='key.json of an earlier run: reuse its window offsets (t0) so '
                                        'the same silver references can score another variant')
    a = ap.parse_args()
    reuse = json.load(open(a.reuse_key, encoding='utf-8')) if a.reuse_key else {}

    rng = random.Random(a.seed)
    dict_en = {l.strip() for l in open(a.lex_en, encoding='utf-8') if l.strip()}
    dict_zh = {l.strip() for l in open(a.lex_zh, encoding='utf-8') if l.strip()}
    os.makedirs(a.silver, exist_ok=True)
    key = {}
    for clip in a.clips:
        segs = {}
        for e in a.engines:
            if e == 'groq':
                p = os.path.join(a.ref, f'{clip}__groq.json')
            else:
                p = os.path.join(a.out, f'{clip}__{e}__{a.variant}.json')
            if os.path.exists(p):
                segs[e] = json.load(open(p, encoding='utf-8'))
        dur = min(s[-1]['end'] for s in segs.values())
        slides_p = os.path.join(a.ref, f'{clip}__slides.json')
        slides = json.load(open(slides_p, encoding='utf-8')) if os.path.exists(slides_p) else []
        note = open(os.path.join(a.ref, f'{clip}__note.md'), encoding='utf-8').read()
        glossary = sorted(term_set(note, dict_zh, dict_en), key=lambda t: (t.isascii(), -len(t), t))[:60]
        usable = dur - a.skip_head - a.win
        edges = [a.skip_head + usable * i / a.k for i in range(a.k + 1)]
        windows = []
        for i in range(a.k):
            wid = f'{clip}#{i + 1:02d}'
            t0 = reuse[wid]['t0'] if wid in reuse else round(rng.uniform(edges[i], edges[i + 1]), 1)
            engines = list(segs)
            rng.shuffle(engines)
            labels = dict(zip('ABC', engines))
            key[wid] = {'t0': t0, 'labels': labels}
            windows.append({'id': wid, 't0': t0, 't1': t0 + a.win,
                            'slide_ocr': slide_text(slides, t0 + a.win / 2),
                            'candidates': {lab: window_text(segs[e], t0, t0 + a.win)
                                           for lab, e in labels.items()}})
        packet = {'clip': clip, 'window_s': a.win, 'glossary': glossary, 'windows': windows}
        with open(os.path.join(a.silver, f'{clip}__packet.json'), 'w', encoding='utf-8') as fh:
            json.dump(packet, fh, ensure_ascii=False, indent=1)
        print(f'{clip}: {len(windows)} windows, engines={list(segs)}, glossary={len(glossary)}')
    with open(os.path.join(a.silver, 'key.json'), 'w', encoding='utf-8') as fh:
        json.dump(key, fh, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
