"""Score full-lecture ASR outputs from bench_run.py.

Metrics per clip x engine:
  cer_groq     character error rate vs the Groq large-v3-turbo transcript (3rd engine,
               NOT a human reference) -- lower = closer to Groq
  cer_x        medium vs breeze disagreement (symmetric)
  term_hit     share of note-vouched terms (Chinese dictionary terms in the note body,
               acronyms / English words of the note's abbreviation table) that at least
               one transcript (Groq or any engine) contains, found verbatim in this output
  term_hit_note  same, without the "some transcript contains it" filter (a floor)
  en_prec / en_capture / garbage   eval_asr.py's lexicon ruler with lexicon/idealab-en.txt
  loops        segments that repeat the previous segment or a 4-gram >= 3x (hallucination loops)
Text is normalised before every comparison: OpenCC s2tw (medium and Groq emit
simplified characters), punctuation and whitespace dropped, Latin lower-cased.

Usage:
    python score_bench.py --out _bench/out --ref _bench/ref --clips idsa-hu idsa-huang emha-feng emha-hung
"""
import argparse
import collections
import json
import os
import re

import jiwer
from opencc import OpenCC

from build_terms import ABBR_ROW, ACRONYM, FRONTMATTER
from eval_asr import STOP, WORD

cc = OpenCC('s2tw')
PUNCT = re.compile(r'[^\w一-鿿]+')
TS = re.compile(r'\[\d+:\d+\]')
GENERIC_EN = STOP | set('''disease patient patients study clinical medical treatment
health care hospital group data figure table page slide year years time use used
level levels high low risk case cases result results effect effects rate'''.split())


def norm(text):
    text = cc.convert(TS.sub(' ', text))
    text = PUNCT.sub('', text)
    return text.lower()


def load_segments(path, max_end=None):
    segs = json.load(open(path, encoding='utf-8'))
    if max_end is not None:
        segs = [s for s in segs if s['start'] < max_end]
    return segs


def text_of(segs):
    return norm(''.join(s['text'] for s in segs))


def loops(segs):
    n = 0
    prev = ''
    for s in segs:
        t = s['text'].strip()
        grams = collections.Counter(t[i:i + 4] for i in range(len(t) - 3))
        if (t and t == prev) or (grams and grams.most_common(1)[0][1] >= 3):
            n += 1
        prev = t
    return n


def en_ruler(raw_text, lex):
    types = {w.lower() for w in WORD.findall(raw_text)} - STOP
    real = {w for w in types if w in lex}
    garbage = sorted(types - real)
    prec = len(real) / len(types) if types else 0.0
    return len(real), len(garbage), prec, garbage


URLISH = re.compile(r'https?://\S+|\([^)]*\.(?:md|docx|png|jpg|html)[^)]*\)|!\[[^\]]*\]|<[^>]+>')


def note_body(note_text):
    """Note text without YAML frontmatter, links, embeds and html."""
    if note_text.startswith('---'):
        end = note_text.find('\n---', 3)
        if end > 0:
            note_text = note_text[end + 4:]
    return URLISH.sub(' ', note_text)


def term_set(note_text, dict_zh, dict_en, spoken_text=None):
    """Terms the note vouches for: Chinese dictionary terms found in the note body, plus
    the acronyms and English full-name words (>= 5 letters, in the English lexicon) of the
    note's own abbreviation table. Optionally restricted to terms also present in spoken_text."""
    body = note_body(note_text)
    n = norm(body)
    terms = {t for t in dict_zh if t in n}
    for line in body.splitlines():
        m = ABBR_ROW.match(line)
        if not m:
            continue
        acr = m.group(1).strip()
        if ACRONYM.match(acr):
            terms.add(acr.lower())
        terms |= {w.lower() for w in WORD.findall(m.group(2))
                  if len(w) >= 5 and w.lower() in dict_en and w.lower() not in GENERIC_EN | FRONTMATTER}
    if spoken_text is not None:
        terms = {t for t in terms if t in spoken_text}
    return terms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='_bench/out')
    ap.add_argument('--ref', default='_bench/ref')
    ap.add_argument('--clips', nargs='+', required=True)
    ap.add_argument('--clip-max-s', type=float, default=3600, help='EMHA refs are full lectures; outputs are the first hour')
    ap.add_argument('--lex-en', default='lexicon/idealab-en.txt')
    ap.add_argument('--lex-zh', default='lexicon/idealab-zh.txt')
    ap.add_argument('--json', default='_bench/scores.json')
    a = ap.parse_args()

    dict_en = {l.strip() for l in open(a.lex_en, encoding='utf-8') if l.strip()}
    dict_zh = {l.strip() for l in open(a.lex_zh, encoding='utf-8') if l.strip()}
    rows, detail = [], {}
    for clip in a.clips:
        outs = sorted(f for f in os.listdir(a.out) if f.startswith(clip + '__') and f.endswith('.json'))
        if not outs:
            continue
        groq_p = os.path.join(a.ref, f'{clip}__groq.json')
        groq = text_of(load_segments(groq_p, a.clip_max_s)) if os.path.exists(groq_p) else None
        note = open(os.path.join(a.ref, f'{clip}__note.md'), encoding='utf-8').read()
        terms_note = term_set(note, dict_zh, dict_en)
        hyp, raws, segs_by = {}, {}, {}
        for f in outs:
            _, tag, variant = f[:-5].split('__')
            segs_by[f] = load_segments(os.path.join(a.out, f))
            raws[f] = ' '.join(s['text'] for s in segs_by[f])
            hyp[(tag, variant)] = text_of(segs_by[f])
        # "spoken" filter: a note term counts only if SOME transcript (Groq or any
        # engine/variant) contains it, so slide-only vocabulary and unspoken full
        # names of acronyms do not drag every engine down equally and uninformatively.
        spoken = ''.join(hyp.values()) + (groq or '')
        terms = term_set(note, dict_zh, dict_en, spoken)
        for f in outs:
            _, tag, variant = f[:-5].split('__')
            segs, raw, txt = segs_by[f], raws[f], hyp[(tag, variant)]
            cap, nbad, prec, bad = en_ruler(raw, dict_en)
            hits = {t for t in terms if t in txt}
            row = {'clip': clip, 'engine': tag, 'variant': variant, 'chars': len(txt),
                   'cer_groq': round(jiwer.cer(groq, txt), 4) if groq else None,
                   'term_n': len(terms), 'term_hit': round(len(hits) / len(terms), 3) if terms else None,
                   'term_note_n': len(terms_note),
                   'term_hit_note': round(len({t for t in terms_note if t in txt}) / len(terms_note), 3) if terms_note else None,
                   'en_capture': cap, 'garbage': nbad, 'en_prec': round(prec, 3), 'loops': loops(segs)}
            rows.append(row)
            detail[f'{clip}/{tag}/{variant}'] = {'missed_terms': sorted(terms - hits)[:60], 'garbage': bad[:40]}
        for variant in {v for _, v in hyp}:
            m, b = hyp.get(('medium', variant)), hyp.get(('breeze25', variant))
            if m and b:
                x = round(jiwer.cer(m, b), 4)
                for r in rows:
                    if r['clip'] == clip and r['variant'] == variant:
                        r['cer_x'] = x

    tim_p = os.path.join(a.out, 'timings.jsonl')
    timings = [json.loads(l) for l in open(tim_p, encoding='utf-8')] if os.path.exists(tim_p) else []
    for r in rows:
        t = [x for x in timings if x['clip'] == r['clip'] and x['tag'] == r['engine'] and x['variant'] == r['variant']]
        if t:
            t = t[-1]
            r.update({'audio_min': round(t['audio_s'] / 60, 1), 'wall_min': round(t['wall_s'] / 60, 1), 'rtf': t['rtf'],
                      'cpu_cores': t['cpu_util_cores'], 'peak_mb': t['peak_rss_mb']})

    cols = ['clip', 'engine', 'variant', 'audio_min', 'wall_min', 'rtf', 'cpu_cores', 'peak_mb',
            'cer_groq', 'cer_x', 'term_n', 'term_hit', 'term_hit_note', 'en_capture', 'garbage', 'en_prec', 'loops']
    print('| ' + ' | '.join(cols) + ' |')
    print('|' + '---|' * len(cols))
    for r in rows:
        print('| ' + ' | '.join('' if r.get(c) is None else str(r.get(c)) for c in cols) + ' |')
    with open(a.json, 'w', encoding='utf-8') as fh:
        json.dump({'rows': rows, 'detail': detail}, fh, ensure_ascii=False, indent=1)
    print(f'\nwrote {a.json}')


if __name__ == '__main__':
    main()
