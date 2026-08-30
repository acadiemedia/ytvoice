# YTVoice: Cloud-Hosted Playhead TTS Engine

A lightweight, portable concatenative text-to-speech (TTS) playhead engine. It allows you to synthesize arbitrary spoken sentences using a single YouTube-hosted video (or a local MP4 file) as a remote voice database.

This project is ideal for developers who want a low-overhead, offline-capable speech synthesizer for desktop apps, custom home servers, Raspberry Pi projects, or smart assistants without the CPU/RAM burden of heavy neural text-to-speech models.

---

## 🛠️ System Requirements & Dependencies

To run this project on **Linux, macOS, Windows, or Termux (Android)**, you must install the following:

### 1. System Binaries (Must be in your System PATH)
* **`ffmpeg`**: Required to decode local video/audio files and handle remote byte-range streaming from YouTube.
* **`mpv`** (or **`ffplay`**): Required for automatic audio playback through your speakers.

*On Ubuntu/Debian:* `sudo apt install ffmpeg mpv`  
*On macOS:* `brew install ffmpeg mpv`  
*On Termux:* `pkg install ffmpeg mpv`

### 2. Python Packages
Install the required packages via `pip`:

```bash
# Required for playback (playhead_synth.py)
pip install pydub yt-dlp

# Required only if compiling a raw ADPCM database (make_database_video.py)
pip install numpy soundfile
```

---

## 🚀 How to Run

### 1. Run Playhead Speech Synthesizer (YouTube Cloud Streaming Mode)
You don't need a local video file! Place your `database_speech.srt` timing file in the directory, specify a YouTube Video ID, and stream the audio slices on-the-fly directly from the cloud:
```bash
python3 playhead_synth.py "hello steve online active" --youtube YOUR_YOUTUBE_VIDEO_ID
```
*Note: This utilizes HTTP byte-range requests to stream only the audio bytes required for each word, keeping bandwidth minimal.*

### 2. Run Playhead Speech Synthesizer (Local File Mode)
For offline local testing, place both `database_speech.srt` and `database_speech.mp4` in the project folder and run:
```bash
python3 playhead_synth.py "hello steve online active"
```

### 3. Compile Database Video (Optional)
If you want to compile your own raw voice sprite database into a H.264 video with 250ms guard bands:
```bash
python3 make_database_video.py
```

---

## 💡 Architecture Concept
* **The Video Map**: The `.srt` file acts as the coordinate mapping database, matching each word to its starting millisecond and duration in the video track.
* **Playhead Stitcher**: The synthesizer seeks the video stream directly to those milliseconds, downloads/reads the short audio slice, strips silence dynamically for clean transitions, and outputs the stitched audio block.
