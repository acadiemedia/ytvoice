#!/usr/bin/env python3
"""
Add common English words that the greedy segmenter currently mis-decomposes
(e.g. 'boil' -> 'bo'+'il' sounding like "boh-ill" instead of "boyl").

Words are phonemized via Piper (espeak) and synthesized in-process, then
resampled to 16kHz mono IMA ADPCM in the same way as the atoms/names tools.

New keys already present in the index are skipped (never overwritten).

Usage:
    python tools/add_common_words.py [--model PATH] [--commit]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import io
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "src"))

import ffmpeg_util  # noqa: E402

# ---------------------------------------------------------------------------
# Common words mis-segmented by greedy longest-prefix matching.
# ---------------------------------------------------------------------------
WORDS = sorted(set([
    # ---- "oi"/"oy" vowel-team family -----------------------------------
    "boil", "boiling", "boiler", "coil", "coiling", "toil", "toiling",
    "foil", "spoil", "spoiling", "broil", "broiler", "hoist", "hoisting",
    "moist", "moisture", "noise", "noisy", "voice", "voyage", "royal",
    "loyal", "royalty", "loyalty", "poison", "poisonous", "void", "avoid",
    "avoidance", "exploit", "exploiting", "employee", "employer",
    "employment", "unemployment", "appoint", "appointment", "disappoint",
    "disappointed", "disappointment", "choice", "choices", "rejoice",
    "rejoicing", "enjoy", "enjoying", "enjoyment", "annoy", "annoying",
    "annoyed", "destroy", "destroyed", "destroying", "boyfriend",
    "girlfriend", "toy", "toys", "boy", "boys", "joy", "joys",

    # ---- "igh" words that are NOT already in the db ---------------------
    "brightly", "brightness", "brighten", "fright", "frighten", "frightening",
    "frightened", "frightful", "delight", "delightful", "delighted",
    "enlighten", "enlightened", "midnight", "fortnight", "tonight",
    "upright", "downright", "outright", "righteous", "alright",

    # ---- "ough" family already partially covered; add stragglers --------
    "thoughtful", "thoughtless", "thoughtfully", "fought", "bought",
    "brought", "sought", "wrought", "draught", "drought", "trough",
    "slough", "borough", "thorough", "thoroughly", "thoroughness",
    "roughly", "toughly", "enough", "cough", "coughing", "dough", "doughy",
    "though", "although", "throughout", "borough", "hickory", "ought",
    "nought", "naught", "naughty", "fraught", "overwrought",

    # ---- "ea"/"ee"/"ei" ambiguous words ----------------------------------
    "leisure", "pleasure", "treasure", "measure", "measured", "measuring",
    "pleasant", "pleasantry", "unpleasant", "breath", "breathe", "breathing",
    "breathtaking", "instead", "already", "ready", "bread", "breakfast",
    "break", "breaking", "steak", "great", "greater", "greatest", "head",
    "ahead", "forehead", "dead", "deadly", "death", "deaf", "heaven",
    "heavy", "heavily", "health", "healthy", "wealth", "wealthy", "stead",
    "steady", "steadily", "thread", "spread", "widespread", "instead",

    # ---- prefixes whose presence misleads the greedy matcher -------------
    "behave", "behavior", "behavioral", "behind", "belief", "believe",
    "believed", "believing", "belong", "belonging", "between", "beneath",
    "beside", "besides", "beyond", "beforehand", "because",
]))


def to_adpcm_wav(ffmpeg, wave_bytes):
    """Resample a 22050Hz mono PCM WAV to 16kHz mono IMA ADPCM WAV bytes."""
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in.wav")
        dst = os.path.join(tmp, "out.wav")
        with open(src, "wb") as f:
            f.write(wave_bytes)
        cmd = [ffmpeg, "-y", "-i", src, "-ar", "16000", "-ac", "1",
               "-c:a", "adpcm_ima_wav", dst]
        subprocess.run(cmd, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        with open(dst, "rb") as f:
            return f.read()


def synth_phonemes(voice, tokens):
    """Synthesize raw phoneme tokens in-process; return PCM WAV bytes."""
    ids = voice.phonemes_to_ids(tokens)
    audio = voice.phoneme_ids_to_audio(ids)
    if isinstance(audio, tuple):
        audio = audio[0]
    if audio.dtype != np.float32:
        audio = audio.astype(np.float32)
    pcm = (audio * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(voice.config.sample_rate)
        f.writeframes(pcm.tobytes())
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser(description="Add common words to voice_sprites.bin")
    ap.add_argument("--model", default=r"X:\piper\voices\en_US-amy-medium.onnx")
    ap.add_argument("--commit", action="store_true",
                    help="Write changes into the repo's bin/index (creates .bak)")
    ap.add_argument("--bulk", type=int, default=0,
                    help="Also synthesize the top-N most frequent English words "
                         "from wordfreq that are missing from the index")
    args = ap.parse_args()

    config_path = args.model + ".json"
    if not os.path.exists(args.model) or not os.path.exists(config_path):
        print(f"[Error] Model or config missing: {args.model}")
        sys.exit(1)

    bin_path = os.path.join(REPO, "voice_sprites.bin")
    index_path = os.path.join(REPO, "voice_sprites.bin.index.json")
    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)

    to_add = [w for w in WORDS if w and w.islower() and w.isascii() and w not in index]

    if args.bulk:
        from wordfreq import top_n_list
        bulk = set()
        for w in top_n_list('en', args.bulk, wordlist='best'):
            wl = w.lower()
            if wl not in bulk and wl and wl.isalpha() and wl.isascii() and len(wl) > 1:
                bulk.add(wl)
        bulk -= set(index)
        extra = sorted(bulk)
        print(f"[*] Bulk: {len(extra)} missing words from top-{args.bulk} English "
              f"frequency list")
        to_add = sorted(set(to_add) | set(extra))

    print(f"[*] {len(to_add)} words to synthesize")

    if not to_add:
        print("[*] Nothing to add.")
        return

    from piper.voice import PiperVoice
    voice = PiperVoice.load(args.model)
    ffmpeg = ffmpeg_util.get_ffmpeg_exe()

    data = bytearray()
    with open(bin_path, "rb") as f:
        data += f.read()

    failed = set()
    offsets = {}
    for i, w in enumerate(to_add):
        if w in failed:
            continue
        try:
            ph = voice.phonemize(w)
            if not ph or not ph[0]:
                failed.add(w)
                continue
            toks = ph[0]
            wav = synth_phonemes(voice, toks)
            blob = to_adpcm_wav(ffmpeg, wav)
        except Exception:
            failed.add(w)
            continue
        if not blob or len(blob) < 128:
            failed.add(w)
            continue
        offsets[w] = [len(data), len(blob)]
        data += blob
        if (i + 1) % 50 == 0:
            print(f"  ... synthesized {i + 1}/{len(to_add)}")

    final_index = dict(index)
    final_index.update(offsets)
    final_blob = bytes(data)

    print(f"[+] Added {len(offsets)} words, total index entries {len(final_index)}")
    if failed:
        print(f"[!] Failed synthesis ({len(failed)}):")
        for w in sorted(failed):
            print(f"    {w!r}")

    new_bin = bin_path + ".new"
    new_index_path = index_path + ".new"
    with open(new_bin, "wb") as f:
        f.write(final_blob)
    with open(new_index_path, "w", encoding="utf-8") as f:
        json.dump(final_index, f)
    print(f"[+] Wrote {new_bin} and {new_index_path}")

    if args.commit:
        for target in (bin_path, index_path):
            if os.path.exists(target):
                os.replace(target, target + ".bak")
        os.replace(new_bin, bin_path)
        os.replace(new_index_path, index_path)
        print("[*] Committed. Backups kept as *.bak")
    else:
        print("[*] Dry run — nothing overwritten. Re-run with --commit.")


if __name__ == "__main__":
    main()