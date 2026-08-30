# YTVoice: Cloud-Hosted Playhead TTS Engine

A lightweight proof-of-concept concatenative text-to-speech playhead engine. It enables low-resource client devices (like microcontrollers or web browsers) to synthesize arbitrary sentences using a YouTube-hosted video as an audio database.

## Architecture

1. **Compilation (`make_database_video.py`)**: 
   Stitches all vocabulary words sequentially into a single continuous audio stream, separated by 250ms guard bands to absorb playback API latency. The output is rendered into an H.264 MP4 video (`database_speech.mp4`), a SubRip subtitle track (`database_speech.srt`), and a text map (`database_map.txt`).

2. **Captions & Indexing**: 
   Uploading the `.srt` caption track to YouTube forces YouTube to display the subtitles in sync and index the audio track, making it searchable.

3. **Synthesis (`test_playhead_synth.py`)**: 
   The client player parses the `.srt` timings in-memory. When given a sentence, it dynamically seeks the video player to the starting millisecond of each word, plays the word for its duration, and pauses—effectively making the video talk.

## Setup & Requirements

Ensure your sandbox or host Termux environment has Python, `ffmpeg`, and the required libraries:

```bash
pip install pydub numpy soundfile
```

## How to Run

### 1. Compile Database Assets
To compile the raw database from a local ADPCM archive:
```bash
python3 make_database_video.py
```
This generates the `.mp4`, `.srt`, and `.txt` files directly onto the SD Card.

### 2. Test Playback Proof of Concept
To stitch a sentence dynamically from the compiled video file using the SRT timings:
```bash
python3 test_playhead_synth.py "hello steve online active"
```

## Global Command Integration
We have mapped the host command `ytvoice` to trigger the player:
```bash
ytvoice "your text here"
```
