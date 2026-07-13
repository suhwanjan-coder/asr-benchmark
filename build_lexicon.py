"""Build a domain lexicon from a corpus of plain-text / markdown documents.

The lexicon is the ruler. It answers exactly one question about a word an ASR
model emitted: does this word exist anywhere in my field's literature, or did
the model invent it?

That is a weaker question than "is this the right word", but it needs no
hand-corrected reference transcript, which is what lets the benchmark scale
past a hand-picked term list.

Usage:
    python build_lexicon.py <corpus_dir> -o lexicon/mine.txt
    python build_lexicon.py <corpus_dir> -o lexicon/mine.txt --min-count 5 --glob '**/*.txt'
"""
import argparse
import collections
import glob
import os
import re

WORD = re.compile(r'[A-Za-z][a-z]{2,}')


def build(corpus_dir, pattern, min_count):
    counts = collections.Counter()
    files = glob.glob(os.path.join(corpus_dir, pattern), recursive=True)
    if not files:
        raise SystemExit(f'no files matched {pattern!r} under {corpus_dir}')
    for i, path in enumerate(files):
        try:
            with open(path, encoding='utf-8', errors='ignore') as fh:
                counts.update(w.lower() for w in WORD.findall(fh.read()))
        except OSError:
            continue
        if i % 2000 == 0:
            print(f'  {i}/{len(files)} files, {len(counts)} unique so far', flush=True)
    # A word must appear >= min_count times somewhere in the whole corpus to
    # count as real. This is what filters OCR noise in the corpus itself
    # without discarding genuinely rare domain terms.
    return {w for w, c in counts.items() if c >= min_count}, len(files)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('corpus_dir', help='directory of .md/.txt documents')
    ap.add_argument('-o', '--out', default='lexicon/mine.txt')
    ap.add_argument('--glob', default='**/*.md', help="default '**/*.md'")
    ap.add_argument('--min-count', type=int, default=3)
    a = ap.parse_args()

    lex, n_files = build(a.corpus_dir, a.glob, a.min_count)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(sorted(lex)) + '\n')
    print(f'lexicon: {len(lex)} words from {n_files} files -> {a.out}')

    # Sanity probe: real domain words should be IN, invented ones OUT.
    # Swap these for words from your own field.
    for probe in ('piriformis', 'pulposus', 'sagittal', 'prolotherapy',
                  'motibra', 'grutius', 'idioma'):
        print(f'   {probe:14} {"IN" if probe in lex else "-- not in lexicon"}')


if __name__ == '__main__':
    main()
