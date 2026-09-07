# YTVoice on Termux / Android (Termux + PRoot)

Step-by-step install for Android phones running Termux, with or without a PRoot Debian sandbox. Tested on Termux + PRoot Debian (Sep 2026).

---

## Quick Install (Termux shell, host side)

The host Termux packages are **required** for audio playback via the linker64 bridge.

```bash
pkg update && pkg upgrade -y
pkg install -y git git-lfs python ffmpeg mpv

# Clone (run from your home; use any folder you like)
git clone https://github.com/acadiemedia/ytvoice.git
cd ytvoice

# Pull the real 238 MB voice database from Git LFS
git lfs install
git lfs pull   # must complete! ~238 MB download

# Install Python deps (pure Python, no compilation)
pip install --break-system-packages -r requirements.txt

# Smoke test — should print "[+] Stitched audio exported ..." and hear "hello steve"
python3 src/player.py "hello steve"
```

---

## Quick Install (PRoot Debian sandbox)

Audio cannot come out of the PRoot `mpv` — PRoot has no direct audio device. YTVoice auto-detects the host Termux mpv and plays through it using the linker64 bridge, so **only Python deps and ffmpeg are needed inside PRoot**:

```bash
apt update && apt install -y git python3 python3-pip ffmpeg
# git-lfs must come from the HOST Termux (ptrace-incompatible), not apt

git clone https://github.com/acadiemedia/ytvoice.git
cd ytvoice

# git lfs installed on host Termux will also work here (it lives on the same filesystem)
git lfs install
git lfs pull

pip install --break-system-packages -r requirements.txt

python3 src/player.py "hello steve"
```

Playback path inside PRoot (automatic, no config):

```
/system/bin/linker64 /data/data/com.termux/files/usr/bin/mpv --no-video <wav>
```

If the host Termux overlay is reachable, you will hear audio. If not, the engine falls back to PRoot `mpv` → `ffplay` → `pydub.playback`, and finally prints `[!] Could not play audio automatically. Output file saved at: /tmp/playhead_proof.wav`.

---

## Verifying the Git LFS pull (most common failure)

`voice_sprites.bin` must be **238,736,226 bytes**. If you see 134 bytes, the LFS object was never downloaded:

```bash
ls -la voice_sprites.bin
# -rw-r--r-- ... 238736226 ...  voice_sprites.bin   <- OK
# -rw-r--r-- ... 134 ...         voice_sprites.bin   <- LFS pointer only!
```

134 bytes means binary mode will report `[!] Failed to extract` for every word. Re-run `git lfs pull`.

---

## Forcing a specific playback mode

* **Binary mode** (fastest, offline): keep `voice_sprites.bin` + `voice_sprites.bin.index.json` in the folder. Auto-selected.
* **Local MP4 mode** (low-memory, offline): keep `database_speech.mp4` + `database_speech.srt`, and rename/remove the `.bin` files.
* **YouTube mode** (zero files, streaming): always pass `--youtube`:
  ```bash
  python3 src/player.py "hello steve" --youtube
  ```

---

## Known issues on this platform

| Symptom | Cause | Fix |
|---|---|---|
| Every word fails extraction | `voice_sprites.bin` is a 134-byte LFS pointer | `git lfs pull` until size shows 238736226 |
| `error: externally-managed-environment` | PEP 668 guard inside Debian PRoot | `pip install --break-system-packages ...` or use a venv |
| No sound from PRoot mpv | PRoot has no audio device access | Uses host mpv via linker64 automatically; `pkg install mpv` on host Termux |
| YouTube mode never activates | Binary files auto-set priority | Pass `--youtube` explicitly |
| Word plays a beep | Word not in database index | Use a different word or run `tools/add_common_words.py` etc. |