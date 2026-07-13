"""Transcribe every clip with ONE model + ONE decoding variant, then exit.

One model per process, on purpose. Loading two models into one process was how
this project produced its first wrong conclusion: on an 8 GB card they fought
over VRAM and the second model looked "2x slower". The measuring instrument was
broken, not the model. Run one, exit, run the next.

Output name is <clip>__<model>__<variant>.txt, which is what eval_asr.py reads.

Usage:
    python transcribe_variants.py <model_path_or_name> <variant> --clips clips/
    python transcribe_variants.py MediaTek-Research/Breeze-ASR-25 novad_nocond
"""
import argparse
import json
import os
import time

from faster_whisper import WhisperModel

# Domain terms fed to hotwords / initial_prompt. In our tests BOTH of these
# made things worse: the model reuses the prompt to invent new wrong words.
# Kept here so you can reproduce the negative result rather than trust it.
TERMS = ('prolotherapy caudal block nucleus pulposus annulus fibrosus fibrocartilage '
         'endplate sagittal plane facet joint vertebra piriformis gluteus medius '
         'sciatic nerve fascia hamstring sacroiliac discogenic pain hydrostatic pressure '
         'disc herniation spondylolisthesis stenosis foramen ligament lidocaine dextrose')

VARIANTS = {
    'base':               dict(beam_size=5,  vad_filter=True),
    'beam10':             dict(beam_size=10, vad_filter=True),
    'hotwords':           dict(beam_size=5,  vad_filter=True, hotwords=TERMS),
    'nocond':             dict(beam_size=5,  vad_filter=True, condition_on_previous_text=False),
    'hot_nocond':         dict(beam_size=5,  vad_filter=True, hotwords=TERMS,
                               condition_on_previous_text=False),
    'nocond_b10':         dict(beam_size=10, vad_filter=True, condition_on_previous_text=False),
    'nocond_rep':         dict(beam_size=5,  vad_filter=True, condition_on_previous_text=False,
                               repetition_penalty=1.15),
    # VAD off beat VAD on across the board for us: the voice-activity filter was
    # eating real speech at segment edges.
    'novad':              dict(beam_size=5,  vad_filter=False),
    'novad_b10':          dict(beam_size=10, vad_filter=False),
    'novad_nocond':       dict(beam_size=5,  vad_filter=False, condition_on_previous_text=False),
    'novad_nocond_b10':   dict(beam_size=10, vad_filter=False, condition_on_previous_text=False),
    'novad_nocond_rep':   dict(beam_size=5,  vad_filter=False, condition_on_previous_text=False,
                               repetition_penalty=1.15),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('model', help='HF id or local CTranslate2 model dir')
    ap.add_argument('variant', choices=sorted(VARIANTS))
    ap.add_argument('--clips', default='clips')
    ap.add_argument('--out', default='out')
    ap.add_argument('--tag', help='short model name used in the filename (default: guessed)')
    ap.add_argument('--language', default='zh')
    ap.add_argument('--device', default='cuda')
    ap.add_argument('--compute-type', default='float16')
    a = ap.parse_args()

    tag = a.tag or os.path.basename(a.model.rstrip('/\\')).lower()
    kwargs = VARIANTS[a.variant]
    os.makedirs(a.out, exist_ok=True)

    t0 = time.time()
    model = WhisperModel(a.model, device=a.device, compute_type=a.compute_type)
    print(f'== {tag}/{a.variant} loaded in {time.time()-t0:.0f}s', flush=True)

    timings = {}
    for f in sorted(os.listdir(a.clips)):
        if not f.endswith(('.wav', '.mp3', '.m4a')):
            continue
        clip = os.path.splitext(f)[0]
        dest = os.path.join(a.out, f'{clip}__{tag}__{a.variant}.txt')
        if os.path.exists(dest):
            continue
        t1 = time.time()
        segments, _ = model.transcribe(os.path.join(a.clips, f), language=a.language, **kwargs)
        lines = [f'[{int(s.start)//60:02d}:{int(s.start)%60:02d}] {s.text.strip()}' for s in segments]
        elapsed = time.time() - t1
        with open(dest, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(lines))
        timings[clip] = round(elapsed, 1)
        print(f'   {clip}: {len(lines)} segments, {elapsed:.0f}s', flush=True)

    with open(os.path.join(a.out, f'time_{tag}_{a.variant}.json'), 'w') as fh:
        json.dump(timings, fh, indent=1)
    print('done', flush=True)


if __name__ == '__main__':
    main()
