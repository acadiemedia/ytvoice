# YTVoice: Cloud-Hosted Concatenative TTS Playhead Engine

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![FFmpeg](https://img.shields.io/badge/dependency-FFmpeg-orange.svg)](https://ffmpeg.org/)

A lightweight, multi-mode concatenative text-to-speech (TTS) playhead engine. It enables low-resource client devices (such as smart home hubs, Termux/Android nodes, Raspberry Pis, or IoT devices) to synthesize arbitrary spoken text on-the-fly. The engine features zero-config YouTube cloud streaming, low-memory local MP4 slicing, and high-performance local binary byte-seeking.

---

## 🐝 The "Bumblebee" Radio Design

Inspired by how the Autobot **Bumblebee** speaks by scanning radio frequencies and stitching audio fragments together, YTVoice treats local or remote video/audio databases as a single cohesive soundboard. 

By mapping word coordinates, the player seeks and slices precise fragments (syllables, words, or sub-words) and concatenates them with natural padding. This eliminates the need to host heavy, resource-intensive neural networks (like Piper or Tortoise-TTS) on small devices.

```mermaid
graph TD
    Text["Input Text (e.g., 'boring')"] --> Tokenizer["Sub-word Tokenizer"]
    Tokenizer -->|"Segmenting unknown words: 'boring' -> 'bor' + 'ing'"| Lookup["Database Lookup"]
    Lookup --> CacheCheck{"Check local .yt_cache/"}
    
    CacheCheck -->|Cache Hit: 0ms| Stitcher["Stitcher Buffer"]
    CacheCheck -->|Cache Miss| ModeDetect{"Auto-Detect Mode"}
    
    ModeDetect -->|1. Binary Database Mode: voice_sprites.bin| DiskSeek["Direct Disk Byte Seek (numpy/soundfile)"]
    ModeDetect -->|2. Local Media Mode: database_speech.mp4| LocalFFmpeg["Local Disk Seek (ffmpeg subprocess)"]
    ModeDetect -->|3. YouTube Cloud Mode: default ID r-WQt6Hi86Y| RemoteFFmpeg["HTTP Range Seek (yt-dlp + ffmpeg)"]
    
    DiskSeek --> WriteCache["Write to .yt_cache/"]
    LocalFFmpeg --> WriteCache
    RemoteFFmpeg --> WriteCache
    
    WriteCache --> Stitcher
    Stitcher --> Cleanup["Trim silent edges (-35dB) & add 35ms pacing"]
    Cleanup --> Playback["Hardware Playback (mpv / ffplay)"]
```

---

## 🛠️ System Setup & Installation

To run this repository on **Linux, macOS, Windows, or Termux (Android)**:

### 1. Install System Binaries
You must have `ffmpeg` (for slicing streams and local media) and `mpv` or `ffplay` (for audio hardware output) installed in your system's path.

* **Ubuntu/Debian**: `sudo apt install ffmpeg mpv`
* **macOS**: `brew install ffmpeg mpv`
* **Termux (Android)**: `pkg install ffmpeg mpv`

### 2. Install Python Dependencies
Clone the repository and install the core Python packages:

```bash
git clone https://github.com/acadiemedia/ytvoice.git
cd ytvoice

# Install playback dependencies (Zero compilation, safe for Termux)
pip install -r requirements.txt
```

*(Note: For Python 3.13+, pip will automatically install the `audioop-lts` backport package since the standard `audioop` module was removed in Python 3.13).*

---

## 🚀 The Three Playback Modes

The player (`src/player.py`) automatically detects which mode to use based on the files present in your directory:

### Mode 1: Zero-Config YouTube Cloud Mode
If no local files are found, the engine automatically defaults to streaming from the official YouTube database video (`r-WQt6Hi86Y`). It downloads the subtitles track in-memory and queries only the specific audio byte-ranges needed.

```bash
# Instant playback out-of-the-box (no local files needed)
python3 src/player.py "hello steve online active"
```
* **Specific Video Streaming**: You can specify another YouTube Video ID/URL:
  ```bash
  python3 src/player.py "hello steve" --youtube YOUR_YOUTUBE_VIDEO_ID
  ```

### Mode 2: High-Performance Binary Database Mode (Default Offline)
If `voice_sprites.bin` and `voice_sprites.bin.index.json` are present in your current directory, the engine boots into high-speed binary seek mode. It queries exact byte offsets from the disk with **0ms seek latency** and zero external subprocess calls.
* **Note**: This mode requires the compiler libraries to parse ADPCM binary files:
  ```bash
  pip install -r requirements-compiler.txt
  python3 src/player.py "hello steve online active"
  ```

### Mode 3: Local MP4 Media Mode (Low-Memory Offline)
If you have `database_speech.mp4` and `database_speech.srt` locally, the player will seek inside the local file using `ffmpeg`. It reads the file on disk instead of loading it entirely into RAM, keeping the memory footprint under **15 MB** (perfect for smart speakers).
* **Bootstrap Offline Files**: You can download these files locally from YouTube automatically:
  ```bash
  python3 src/player.py --download r-WQt6Hi86Y
  ```
  This creates `database_speech.srt` and `database_speech.mp4` in your folder. Play offline using:
  ```bash
  python3 src/player.py "hello steve online active"
  ```

---

## 🧠 Smart Engine Features

### 1. Greedy Sub-Word Segmentation Tokenizer
If you speak a composite or unknown word (such as `"boring"` or `"haba"`), the engine recursively matches the longest dictionary prefixes against the database:
* `"boring"` $\rightarrow$ segments and stitches `"bor"` + `"ing"`.
* `"haba"` $\rightarrow$ segments and stitches `"ha"` + `"ba"`.
This expands your vocabulary coverage dynamically without manually compiling new audio sets.

### 2. On-Demand Local Caching
When in YouTube mode, each fetched word segment is saved locally inside a `.yt_cache/` directory. Subsequent playback of the same word reads it directly from disk. If all words in a sentence are cached, the engine **bypasses YouTube and the network entirely**, starting playback in under 50ms.

---

## 🛠️ CLI Flags Help

Run `python3 src/player.py --help` to see all available execution flags:

| Flag | Default | Description |
|---|---|---|
| `sentence` | (Optional) | The sentence to synthesize and speak. |
| `--youtube` | `r-WQt6Hi86Y` | YouTube Video ID or URL to stream from on-the-fly. Defaults to the official database when passed without an argument. |
| `--srt` | `database_speech.srt` | Path to the local SRT subtitle timing mapping. |
| `--audio` | `database_speech.mp4` | Path to the local MP4 video/audio database. |
| `--cache-dir` | `.yt_cache` | Directory to cache retrieved audio slices (YouTube mode). |
| `--bin` | `voice_sprites.bin` | Path to the binary ADPCM database file. |
| `--index` | `voice_sprites.bin.index.json` | Path to the JSON binary index mapping. |
| `--download` | `None` | Bootstraps both `srt` and `mp4` locally from YouTube for offline usage. |

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
