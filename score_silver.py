"""Score engines against the judge-written silver references (see make_windows.py).

Reads <silver>/<clip>__silver.json = [{"id": "...", "reference": "..."}], unblinds with
key.json and prints micro-CER per clip x engine plus per-window wins and a two-sided
sign test (medium vs breeze25).

Usage:
    python score_silver.py --clips idsa-hu idsa-huang emha-feng emha-hung
"""
import argparse
import collections
import json
import math
import os

import re

import jiwer

from score_bench import norm

# Mandarin fillers / discourse particles. Whisper-family models tend to drop them,
# Breeze tends to keep them; neither matters for note-writing, so a second CER is
# computed with them removed from both sides (sensitivity analysis).
FILLERS = re.compile(r'(那個|這個|就是|然後|所以說|其實|那麼|那|就|嗯|呃|啊|喔|哦|欸|耶|啦|吧|呢|對|好|齁|嘛)')


def strip_fillers(t):
    return FILLERS.sub('', t)


def sign_test(wins_a, wins_b):
    n = wins_a + wins_b
    if n == 0:
        return 1.0
    k = min(wins_a, wins_b)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--silver', default='_bench/silver')
    ap.add_argument('--clips', nargs='+', required=True)
    ap.add_argument('--judge', default='', help="suffix of the silver file, e.g. _j1 -> <clip>__silver_j1.json")
    ap.add_argument('--json', default='_bench/scores_silver.json')
    a = ap.parse_args()
    key = json.load(open(os.path.join(a.silver, 'key.json'), encoding='utf-8'))
    per = {}
    rows = []
    for clip in a.clips:
        packet = json.load(open(os.path.join(a.silver, f'{clip}__packet.json'), encoding='utf-8'))
        silver_list = json.load(open(os.path.join(a.silver, f'{clip}__silver{a.judge}.json'), encoding='utf-8'))
        silver = {w['id']: w['reference'] for w in silver_list}
        agg = {}
        wins = {'medium': 0, 'breeze25': 0, 'tie': 0}
        for w in packet['windows']:
            ref = norm(silver.get(w['id'], ''))
            if not ref:
                continue
            labels = key[w['id']]['labels']
            cers = {}
            for lab, eng in labels.items():
                hyp = norm(w['candidates'][lab])
                d = jiwer.process_characters(ref, hyp)
                errs = d.substitutions + d.deletions + d.insertions
                r2, h2 = strip_fillers(ref), strip_fillers(hyp)
                d2 = jiwer.process_characters(r2, h2)
                x = agg.setdefault(eng, {'errs': 0, 'ref': 0, 'n': 0, 'sub': 0, 'del': 0, 'ins': 0, 'errs_nf': 0, 'ref_nf': 0})
                x['errs'] += errs
                x['ref'] += len(ref)
                x['n'] += 1
                x['sub'] += d.substitutions
                x['del'] += d.deletions
                x['ins'] += d.insertions
                x['errs_nf'] += d2.substitutions + d2.deletions + d2.insertions
                x['ref_nf'] += len(r2)
                cers[eng] = errs / len(ref)
                per[w['id'] + '/' + eng] = round(cers[eng], 3)
            if 'medium' in cers and 'breeze25' in cers:
                if abs(cers['medium'] - cers['breeze25']) < 1e-9:
                    wins['tie'] += 1
                elif cers['medium'] < cers['breeze25']:
                    wins['medium'] += 1
                else:
                    wins['breeze25'] += 1
        for eng, x in agg.items():
            rows.append({'clip': clip, 'engine': eng, 'windows': x['n'], 'ref_chars': x['ref'],
                         'cer_silver': round(x['errs'] / x['ref'], 4),
                         'sub': round(x['sub'] / x['ref'], 4), 'del': round(x['del'] / x['ref'], 4),
                         'ins': round(x['ins'] / x['ref'], 4), 'cer_nofiller': round(x['errs_nf'] / x['ref_nf'], 4)})
        p = sign_test(wins['medium'], wins['breeze25'])
        rows.append({'clip': clip, 'engine': 'wins medium/breeze/tie',
                     'windows': '%d/%d/%d' % (wins['medium'], wins['breeze25'], wins['tie']),
                     'ref_chars': '', 'cer_silver': 'sign p=%.2f' % p, 'sub': '', 'del': '', 'ins': '', 'cer_nofiller': ''})
    tot = {}
    for r in rows:
        if isinstance(r['ref_chars'], int):
            t = tot.setdefault(r['engine'], collections.Counter())
            n = r['ref_chars']
            t['w'] += r['windows']
            t['n'] += n
            for k in ('cer_silver', 'sub', 'del', 'ins', 'cer_nofiller'):
                t[k] += r[k] * n
    for eng, t in tot.items():
        rows.append({'clip': 'ALL', 'engine': eng, 'windows': t['w'], 'ref_chars': t['n'],
                     **{k: round(t[k] / t['n'], 4) for k in ('cer_silver', 'sub', 'del', 'ins', 'cer_nofiller')}})
    cols = ['clip', 'engine', 'windows', 'ref_chars', 'cer_silver', 'sub', 'del', 'ins', 'cer_nofiller']
    print('| ' + ' | '.join(cols) + ' |')
    print('|' + '---|' * len(cols))
    for r in rows:
        print('| ' + ' | '.join(str(r.get(c, '')) for c in cols) + ' |')
    with open(a.json, 'w', encoding='utf-8') as fh:
        json.dump({'rows': rows, 'per_window': per}, fh, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
