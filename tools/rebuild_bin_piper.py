#!/usr/bin/env python3
"""
Rebuild voice_sprites.bin with high-quality Piper (en_US-amy) audio.

Each dictionary word is spoken by Piper at 22.05kHz mono, resampled to
16kHz mono and encoded as IMA ADPCM WAV (the same container format the
existing sprites use), then all sprites are concatenated into a new
voice_sprites.bin with a regenerated index.

Usage:
    python tools/rebuild_bin_piper.py [--model PATH] [--batch N] [--commit]

Defaults:
    --model  X:\\piper\\voices\\en_US-amy-medium.onnx
    --batch  1000 words per Piper invocation
    --commit overwrites the repo's voice_sprites.bin / index (creates
            .bak backups first). Without --commit, outputs are written
            as *.new and nothing in the repo is touched.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "src"))

import ffmpeg_util  # noqa: E402

KEEP_PATTERN = re.compile(r"^[a-z ]+$")
PRESERVE_RAW = {"glitch_1"}  # sound-effect tokens, copied byte-for-byte


def load_old_index(index_path):
    with open(index_path, "r", encoding="utf-8") as f:
        return json.load(f)


def keep_key(k):
    # "i" is a real English word and must be spoken (use the batch `-i`/`-d`
    # path for it — piper's single-arg stdin mode drops a lone "i"/"I").
    if k == "i":
        return True
    return len(k) >= 2 and bool(KEEP_PATTERN.fullmatch(k))


def run_piper_batch(model, config, lines):
    """Speak `lines` once (model loaded once). Returns {line: wav_bytes}."""
    with tempfile.TemporaryDirectory() as tmp:
        in_txt = os.path.join(tmp, "in.txt")
        out_dir = os.path.join(tmp, "out")
        os.makedirs(out_dir, exist_ok=True)
        with open(in_txt, "w", encoding="utf-8") as f:
            for ln in lines:
                f.write(ln + "\n")
        cmd = [
            "piper", "-m", model, "-c", config,
            "-i", in_txt, "-d", out_dir,
            "--output-dir-naming", "text",
            "--sentence-silence", "0.05",
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        result = {}
        for ln in lines:
            wav = os.path.join(out_dir, ln + ".wav")
            if os.path.exists(wav):
                with open(wav, "rb") as f:
                    result[ln] = f.read()
        return result


def to_adpcm_wav(ffmpeg, wav_bytes):
    """Resample a 22.05kHz mono WAV to 16kHz mono IMA ADPCM WAV bytes."""
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in.wav")
        dst = os.path.join(tmp, "out.wav")
        with open(src, "wb") as f:
            f.write(wav_bytes)
        cmd = [
            ffmpeg, "-y",
            "-i", src,
            "-ar", "16000", "-ac", "1",
            "-c:a", "adpcm_ima_wav",
            dst,
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        with open(dst, "rb") as f:
            return f.read()


def rebuild(model, config, old_index, old_bin, batch_size, progress):
    ffmpeg = ffmpeg_util.get_ffmpeg_exe()

    keep_words = [k for k in old_index if keep_key(k)]
    preserve_words = [k for k in PRESERVE_RAW if k in old_index]
    keep_words.sort()
    preserve_words.sort()

    print(f"[*] Words to re-speak with Piper: {len(keep_words)}")
    if preserve_words:
        print(f"[*] Preserved raw (copied from old bin): {preserve_words}")

    # Copy preserved sprites straight through.
    data = bytearray()
    old_bin_file = open(old_bin, "rb")
    new_index = {}
    try:
        for k in preserve_words:
            off, ln = old_index[k]
            old_bin_file.seek(off)
            blob = old_bin_file.read(ln)
            new_index[k] = [len(data), len(blob)]
            data += blob

        done = 0
        failed = []
        total = len(keep_words)
        for start in range(0, total, batch_size):
            batch = keep_words[start:start + batch_size]
            spoken = run_piper_batch(model, config, batch)
            for k in batch:
                wav = spoken.get(k)
                if not wav:
                    failed.append(k)
                    continue
                try:
                    blob = to_adpcm_wav(ffmpeg, wav)
                except Exception:
                    failed.append(k)
                    continue
                new_index[k] = [len(data), len(blob)]
                data += blob
                done += 1
            if progress:
                print(f"[*] {done}/{total} words encoded")
    finally:
        old_bin_file.close()

    if failed:
        print(f"[!] {len(failed)} words failed batch synthesis; retrying individually...")
        retry_failed = []
        for k in failed:
            try:
                wav = run_piper_batch(model, config, [k]).get(k)
                if wav:
                    blob = to_adpcm_wav(ffmpeg, wav)
                    new_index[k] = [len(data), len(blob)]
                    data += blob
                    done += 1
                    continue
            except Exception:
                pass
            retry_failed.append(k)
        if retry_failed:
            print(f"[!] Still missing {len(retry_failed)} words (will be excluded): "
                  f"{retry_failed[:20]}")

    return bytes(data), new_index, done


def main():
    ap = argparse.ArgumentParser(description="Rebuild voice_sprites.bin with Piper")
    ap.add_argument("--model", default=r"X:\piper\voices\en_US-amy-medium.onnx")
    ap.add_argument("--batch", type=int, default=1000)
    ap.add_argument("--commit", action="store_true",
                    help="Overwrite repo voice_sprites.bin(+index); creates .bak backups")
    ap.add_argument("--progress", action="store_true", help="Print per-batch progress")
    args = ap.parse_args()

    config = args.model + ".json"
    if not os.path.exists(args.model) or not os.path.exists(config):
        print(f"[Error] Model or config missing: {args.model}")
        sys.exit(1)

    old_bin = os.path.join(REPO, "voice_sprites.bin")
    old_index_path = os.path.join(REPO, "voice_sprites.bin.index.json")
    old_index = load_old_index(old_index_path)

    print(f"[*] Model: {args.model}")
    blob, new_index, done = rebuild(
        args.model, config, old_index, old_bin, args.batch, args.progress
    )

    new_bin = os.path.join(REPO, "voice_sprites.bin.new")
    new_index_path = os.path.join(REPO, "voice_sprites.bin.index.json.new")
    with open(new_bin, "wb") as f:
        f.write(blob)
    with open(new_index_path, "w", encoding="utf-8") as f:
        json.dump(new_index, f)

    print(f"[+] Encoded {done} words, total entries {len(new_index)}")
    print(f"[+] New bin:    {new_bin} ({len(blob)} bytes)")
    print(f"[+] New index:  {new_index_path}")

    if args.commit:
        for target in (old_bin, old_index_path):
            if os.path.exists(target):
                os.replace(target, target + ".bak")
        os.replace(new_bin, old_bin)
        os.replace(new_index_path, old_index_path)
        print("[*] Committed: replaced voice_sprites.bin(.index.json); backups as .bak")
    else:
        print("[*] Dry run — nothing overwritten. Re-run with --commit to apply.")


if __name__ == "__main__":
    main()
