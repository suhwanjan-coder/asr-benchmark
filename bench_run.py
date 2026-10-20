"""Transcribe full-length lecture audio with ONE model, record wall time / CPU / RAM.

One model per process (see transcribe_variants.py for why). Writes, per audio file:
  <out>/<clip>__<tag>__<variant>.json   segments [{start, end, text}]
  <out>/<clip>__<tag>__<variant>.txt    one segment per line
and appends one row per clip to <out>/timings.jsonl.

Usage:
    python bench_run.py <model> <variant> --tag medium --audio a.wav b.wav --out _bench/out
    python bench_run.py models/breeze-asr-25-ct2 novad_nocond --tag breeze25 --audio ... --threads 16
"""
import argparse
import json
import os
import platform
import threading
import time

import psutil
from faster_whisper import WhisperModel

from transcribe_variants import VARIANTS


class PeakRss(threading.Thread):
    """Poll this process RSS every 0.5 s; keep the peak (MB)."""
    def __init__(self):
        super().__init__(daemon=True)
        self.proc = psutil.Process()
        self.peak = 0.0
        self.stop = threading.Event()

    def run(self):
        while not self.stop.is_set():
            self.peak = max(self.peak, self.proc.memory_info().rss / 2**20)
            self.stop.wait(0.5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('model')
    ap.add_argument('variant', choices=sorted(VARIANTS))
    ap.add_argument('--tag', required=True)
    ap.add_argument('--audio', nargs='+', required=True)
    ap.add_argument('--out', default='_bench/out')
    ap.add_argument('--language', default='zh')
    ap.add_argument('--threads', type=int, default=16)
    ap.add_argument('--compute-type', default='int8')
    ap.add_argument('--hotwords-file', help='text file; contents passed as hotwords= to transcribe()')
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    kwargs = dict(VARIANTS[a.variant])
    variant = a.variant
    if a.hotwords_file:
        # Same decoding settings as the base variant, plus the shared hotword list.
        with open(a.hotwords_file, encoding='utf-8') as fh:
            kwargs['hotwords'] = ' '.join(fh.read().split())
        variant += '_hot'

    rss = PeakRss()
    rss.start()
    t0 = time.time()
    model = WhisperModel(a.model, device='cpu', compute_type=a.compute_type, cpu_threads=a.threads)
    load_s = time.time() - t0
    print(f'== {a.tag}/{variant} loaded in {load_s:.0f}s threads={a.threads}', flush=True)

    proc = psutil.Process()
    for path in a.audio:
        clip = os.path.splitext(os.path.basename(path))[0]
        stem = f'{clip}__{a.tag}__{variant}'
        cpu0 = proc.cpu_times()
        t1 = time.time()
        segs_iter, info = model.transcribe(path, language=a.language, **kwargs)
        segs = []
        for s in segs_iter:
            segs.append({'start': round(s.start, 2), 'end': round(s.end, 2), 'text': s.text.strip()})
            if len(segs) % 200 == 0:
                print(f'   {clip}: {len(segs)} segs @ {s.end/60:.1f} min, {time.time()-t1:.0f}s', flush=True)
        wall = time.time() - t1
        cpu1 = proc.cpu_times()
        cpu_s = (cpu1.user - cpu0.user) + (cpu1.system - cpu0.system)
        with open(os.path.join(a.out, stem + '.json'), 'w', encoding='utf-8') as fh:
            json.dump(segs, fh, ensure_ascii=False, indent=1)
        with open(os.path.join(a.out, stem + '.txt'), 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(s['text'] for s in segs) + '\n')
        row = {
            'clip': clip, 'tag': a.tag, 'variant': variant, 'model': a.model,
            'audio_s': round(info.duration, 1), 'wall_s': round(wall, 1), 'load_s': round(load_s, 1),
            'rtf': round(wall / info.duration, 3), 'cpu_s': round(cpu_s, 1),
            'cpu_util_cores': round(cpu_s / wall, 2), 'peak_rss_mb': round(rss.peak),
            'threads': a.threads, 'compute_type': a.compute_type, 'n_segments': len(segs),
            'hotwords': bool(a.hotwords_file), 'host': platform.node(),
            'ts': time.strftime('%Y-%m-%dT%H:%M:%S'),
        }
        with open(os.path.join(a.out, 'timings.jsonl'), 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + '\n')
        print(f'== {stem}: {info.duration/60:.1f} min audio in {wall/60:.1f} min '
              f'(rtf {wall/info.duration:.2f}, {len(segs)} segs, peak {rss.peak:.0f} MB)', flush=True)
    rss.stop.set()


if __name__ == '__main__':
    main()
