"""Build the shared dictionary (English lexicon + Chinese terms + hotwords) from an
Obsidian vault of medical / EMHA cards.

Outputs (all under lexicon/):
  idealab-en.txt   English word-types, >= --min-count occurrences in the corpus
                   (same rule as build_lexicon.py; used for precision / garbage)
  idealab-zh.txt   Chinese terms: abbreviation-table entries (curated) plus jieba
                   noun tokens with document frequency >= --zh-min-df and
                   <= --zh-max-df-share of all files (drops function-like words)
  hotwords.txt     one line, the SAME hotword string given to every engine:
                   top --n-hot Chinese + top --n-hot English terms by document frequency
  terms_meta.json  counts and settings, for the report

Usage:
    python build_terms.py C:/Users/suhwa/dev/idea-lab --dirs 02-Clinical 06-EMHA 03-Research 00-Inbox
        --exclude 20261004_胡婉妍 20261004_黃立民
"""
import argparse
import collections
import glob
import json
import os
import re
import sys

import jieba

from build_lexicon import WORD
from eval_asr import STOP

CJK = re.compile(r'^[\u4e00-\u9fff]{2,6}$')
# | ABBR | English full name | 中文 | — rows of the 縮寫表 tables in lecture notes
ABBR_ROW = re.compile(r'^\|\s*([A-Z][A-Za-z0-9/\-\+]{1,11})\s*\|\s*([A-Za-z][^|]{3,90})\|\s*([^|]{2,60})\|')
ACRONYM = re.compile(r'^(?=(?:.*[A-Z]){2})[A-Z0-9][A-Za-z0-9/\-\+]*$')
ZH_SKIP = {'待補', '待確認', '未定'}
FRONTMATTER = set('''title status source published tags aliases type date created modified
note notes lecture slide slides summary figure figures section speaker topic draft'''.split())
GENERIC_EN = STOP | set('''disease patient patients study clinical medical treatment
health care hospital group data figure table page slide year years time use used
level levels high low risk case cases result results effect effects rate'''.split())


def iter_files(root, dirs, excludes):
    for d in dirs:
        for p in glob.glob(os.path.join(root, d, '**', '*.md'), recursive=True):
            if any(x in p for x in excludes):
                continue
            yield p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('vault')
    ap.add_argument('--dirs', nargs='+', default=['02-Clinical', '06-EMHA', '03-Research', '00-Inbox'])
    ap.add_argument('--exclude', nargs='*', default=[], help='substrings of paths to leave out (test lectures)')
    ap.add_argument('--min-count', type=int, default=3)
    ap.add_argument('--zh-min-df', type=int, default=5)
    ap.add_argument('--zh-max-df-share', type=float, default=0.25)
    ap.add_argument('--n-hot', type=int, default=40)
    ap.add_argument('--out-dir', default='lexicon')
    ap.add_argument('--tokenizer', default='models/whisper-medium-ct2/tokenizer.json')
    ap.add_argument('--token-budget', type=int, default=200)
    a = ap.parse_args()

    files = list(iter_files(a.vault, a.dirs, a.exclude))
    en_counts, en_df = collections.Counter(), collections.Counter()
    zh_df, abbr_zh, abbr_en, abbr_words = (collections.Counter() for _ in range(4))
    for i, p in enumerate(files):
        with open(p, encoding='utf-8', errors='ignore') as fh:
            text = fh.read()
        words = [w.lower() for w in WORD.findall(text)]
        en_counts.update(words)
        en_df.update(set(words))
        for line in text.splitlines():
            m = ABBR_ROW.match(line)
            if not m or set(m.group(1)) <= set('-: '):
                continue
            acr = m.group(1).strip()
            if ACRONYM.match(acr):
                abbr_en[acr] += 1
            abbr_words.update({w.lower() for w in WORD.findall(m.group(2)) if len(w) >= 5})
            for zh in re.split(r'[／/、；;，,（(]', m.group(3)):
                zh = zh.strip()
                if CJK.match(zh):
                    abbr_zh[zh] += 1
        toks = {w for w in jieba.lcut(text, HMM=False) if CJK.match(w)}
        zh_df.update(toks)
        if i % 200 == 0:
            print(f'  {i}/{len(files)} files', file=sys.stderr, flush=True)

    n = len(files)
    en_lex = {w for w, c in en_counts.items() if c >= a.min_count}
    zh_generic_cut = a.zh_max_df_share * n
    # 2-character jieba tokens are mostly general vocabulary (做法, 途中); keep
    # >= 3 characters from jieba, and every curated abbreviation-table entry.
    zh_terms = {w for w, d in zh_df.items() if len(w) >= 3 and a.zh_min_df <= d <= zh_generic_cut}
    zh_terms |= set(abbr_zh) - ZH_SKIP

    # Hotwords, all from the curated abbreviation tables: Chinese names, spoken
    # acronyms, English full-name words; ranked by document frequency and trimmed
    # to the Whisper prompt budget (faster-whisper keeps the last 223 prompt tokens).
    zh_hot = [w for w, _ in abbr_zh.most_common() if w not in ZH_SKIP][:a.n_hot]
    acr_hot = [w for w, _ in abbr_en.most_common()][:a.n_hot // 2]
    en_hot = [w for w, _ in abbr_words.most_common()
              if w in en_lex and w not in GENERIC_EN and w not in FRONTMATTER][:a.n_hot // 2]
    groups = [zh_hot, acr_hot, en_hot]
    tok = None
    if a.tokenizer and os.path.exists(a.tokenizer):
        from tokenizers import Tokenizer
        tok = Tokenizer.from_file(a.tokenizer)
    def n_tokens():
        hot = ' '.join(w for g in groups for w in g)
        return len(tok.encode(hot).ids) if tok else len(hot.split())
    while tok and n_tokens() > a.token_budget:
        longest = max(groups, key=len)
        longest.pop()
    hot = ' '.join(w for g in groups for w in g)
    print(f'hotword prompt tokens: {n_tokens()} (budget {a.token_budget})')

    os.makedirs(a.out_dir, exist_ok=True)
    with open(os.path.join(a.out_dir, 'idealab-en.txt'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(sorted(en_lex)) + '\n')
    with open(os.path.join(a.out_dir, 'idealab-zh.txt'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(sorted(zh_terms)) + '\n')
    with open(os.path.join(a.out_dir, 'hotwords.txt'), 'w', encoding='utf-8') as fh:
        fh.write(hot + '\n')
    meta = {'files': n, 'dirs': a.dirs, 'exclude': a.exclude, 'min_count': a.min_count,
            'zh_min_df': a.zh_min_df, 'zh_max_df_share': a.zh_max_df_share,
            'en_lexicon': len(en_lex), 'zh_terms': len(zh_terms), 'zh_from_abbr_tables': len(abbr_zh),
            'hotwords_zh': zh_hot, 'hotwords_acronyms': acr_hot, 'hotwords_en': en_hot}
    with open(os.path.join(a.out_dir, 'terms_meta.json'), 'w', encoding='utf-8') as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=1)
    print(f'files={n} en={len(en_lex)} zh={len(zh_terms)} (abbr-table {len(abbr_zh)}) hotwords={len(hot.split())}')
    print('hot zh:', zh_hot)
    print('hot acronyms:', acr_hot)
    print('hot en:', en_hot)


if __name__ == '__main__':
    main()
