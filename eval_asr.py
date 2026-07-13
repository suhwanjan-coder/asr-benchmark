"""Score ASR transcripts against a domain lexicon. No ground truth needed.

Read the two numbers TOGETHER, they fail in opposite directions:

  PRECISION = of the latin word-types the model emitted, what share are real
              words (present in the lexicon). Catches invented garbage:
              motibra, grutius, idioma.
  CAPTURE   = how many DISTINCT real word-types it managed to emit at all.
              Catches the opposite failure: a model that simply doesn't hear
              English would score 100% precision while capturing nothing.

Plus an optional CJK sanity check: terms that MUST survive intact in your
recordings, and known mis-hearings you want flagged. A model that mangles
椎間盤突出 into 最艱難突出 loses here even if its English is perfect.

Honest about what CAPTURE is: it counts real *word-types*, not curated domain
terms. The lexicon is "every word that appears in my field's books", so common
English words are in it too (a short stoplist removes the most frequent ones).
It is a garbage detector and a coverage proxy, not a terminology accuracy score.

Input files must be named:  <clip>__<model>__<variant>.txt

Usage:
    python eval_asr.py out/ --lexicon lexicon/pmr-en.txt
    python eval_asr.py out/ --lexicon lexicon/mine.txt --domain domain.json
"""
import argparse
import collections
import json
import os
import re

WORD = re.compile(r'[A-Za-z][a-z]{2,}')
TIMESTAMP = re.compile(r'\[\d+:\d+\]')

# Very common English words carry no signal about domain-vocabulary quality: a
# model gets no credit for "the", and no blame either. Score on the rest.
STOP = set('''the and for you that this with are was but not have has can all
your out get one two see here there they them from what when how why now just
some very like also more most only than then their these those which while
who whom into over under about after before between during okay yeah right
good well much many such each other another because our their his her its
would could should will shall may might must does did done doing'''.split())


def score(path, lex, must, known_bad):
    with open(path, encoding='utf-8') as fh:
        body = TIMESTAMP.sub(' ', fh.read())
    types = {w.lower() for w in WORD.findall(body)} - STOP
    valid = {t for t in types if t in lex}
    garbage = types - valid
    return {
        'capture': len(valid),
        'garbage_n': len(garbage),
        'precision': len(valid) / max(len(types), 1),
        'cjk_ok': sum(1 for t in must if t in body),
        'cjk_bad': sum(body.count(b) for b in known_bad),
        'garbage': sorted(garbage)[:8],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out_dir', help='dir of <clip>__<model>__<variant>.txt')
    ap.add_argument('--lexicon', default='lexicon/pmr-en.txt')
    ap.add_argument('--domain', help='JSON with must_survive / known_bad (see domain.example.json)')
    a = ap.parse_args()

    with open(a.lexicon, encoding='utf-8') as fh:
        lex = {line.strip() for line in fh if line.strip()}
    must, known_bad = [], []
    if a.domain:
        cfg = json.load(open(a.domain, encoding='utf-8'))
        must = cfg.get('must_survive', [])
        known_bad = cfg.get('known_bad', [])

    rows = collections.defaultdict(dict)
    for f in sorted(os.listdir(a.out_dir)):
        if not f.endswith('.txt'):
            continue
        try:
            clip, model, variant = f[:-4].split('__')
        except ValueError:
            print(f'skip (bad name): {f}')
            continue
        rows[clip][(model, variant)] = score(os.path.join(a.out_dir, f), lex, must, known_bad)

    combos = sorted({k for v in rows.values() for k in v})
    agg = {c: collections.defaultdict(float) for c in combos}
    for per_combo in rows.values():
        for c in combos:
            s = per_combo.get(c)
            if not s:
                continue
            for k in ('capture', 'garbage_n', 'cjk_ok', 'cjk_bad'):
                agg[c][k] += s[k]
            agg[c]['n'] += 1
            agg[c]['prec_sum'] += s['precision']

    print(f'{"model/variant":26} {"n":>3} {"capture":>8} {"garbage":>8} {"precision":>10} {"cjk✓":>6} {"cjk✗":>6}')
    print('-' * 74)
    for c in combos:
        g = agg[c]
        if not g['n']:
            continue
        print(f'{c[0]+"/"+c[1]:26} {int(g["n"]):>3} {int(g["capture"]):>8} {int(g["garbage_n"]):>8} '
              f'{g["prec_sum"]/g["n"]:>9.1%} {int(g["cjk_ok"]):>6} {int(g["cjk_bad"]):>6}')

    print('\nmost-invented garbage per combo (this is where the hallucinations show):')
    for c in combos:
        bad = collections.Counter()
        for per_combo in rows.values():
            if c in per_combo:
                bad.update(per_combo[c]['garbage'])
        print(f'  {c[0]}/{c[1]:16} {[w for w, _ in bad.most_common(8)]}')


if __name__ == '__main__':
    main()
