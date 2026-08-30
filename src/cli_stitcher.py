import sys
import os
import io
import subprocess
import argparse
import soundfile as sf
import numpy as np
from pydub import AudioSegment

# Import our local portable SpriteExtractor from compiler.py
from compiler import SpriteExtractor

def stitch_clip(sentence, bin_path, index_path, output_mp4):
    print(f"[*] Loading database index from: {index_path}")
    extractor = SpriteExtractor(bin_path, index_path)
    
    words = sentence.lower().replace(",", "").replace(".", "").split()
    pcm_chunks = []
    timings = []
    
    BYTES_PER_MS = 32
    SAMPLE_RATE = 16000
    GUARD_BAND_MS = 250
    
    print(f"[*] Stitching sentence: '{sentence}'")
    for w in words:
        raw_data = extractor.extract_sprite(w)
        if raw_data is None:
            print(f"  [!] Word '{w}' not found in database! Skipping.")
            continue
            
        try:
            data, sr = sf.read(io.BytesIO(raw_data))
            int16_samples = (data * 32767).astype(np.int16)
            pcm_bytes = int16_samples.tobytes()
        except Exception as e:
            print(f"  [-] Error decoding '{w}': {e}")
            continue
            
        duration_ms = len(pcm_bytes) / BYTES_PER_MS
        pcm_chunks.append(pcm_bytes)
        
        # Add 250ms guard band silence
        silence_pad = b"\x00" * (GUARD_BAND_MS * BYTES_PER_MS)
        pcm_chunks.append(silence_pad)
        
        # Track timing
        timings.append(duration_ms + GUARD_BAND_MS)
        
    if not pcm_chunks:
        print("[Error] No words were successfully stitched.")
        sys.exit(1)
        
    # Export raw WAV
    temp_wav = "/tmp/clip_temp.wav"
    raw_pcm_data = b"".join(pcm_chunks)
    master_segment = AudioSegment(data=raw_pcm_data, sample_width=2, frame_rate=SAMPLE_RATE, channels=1)
    master_segment.export(temp_wav, format="wav")
    
    # YouTube timestamps description mapping
    print("\n--- YOUTUBE DESCRIPTION MAP ---")
    current_ms = 0.0
    for idx, w in enumerate(words):
        seconds = int(current_ms / 1000)
        minutes = seconds // 60
        secs = seconds % 60
        print(f"{minutes:02d}:{secs:02d} - {w}")
        if idx < len(timings):
            current_ms += timings[idx]
    print("--------------------------------\n")
    
    # Convert to MP4 using ffmpeg
    print(f"[*] Packaging as MP4 to: {output_mp4}")
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=640x360",
        "-i", temp_wav,
        "-c:v", "libx264", "-tune", "stillimage",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        output_mp4
    ]
    subprocess.run(cmd, check=True)
    print(f"[+] Video successfully saved to: {output_mp4}")
    
    if os.path.exists(temp_wav):
        os.remove(temp_wav)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YTVoice Single Clip Video Stitcher")
    parser.add_argument("sentence", help="Text to speak")
    parser.add_argument("--bin", default="voice_sprites.bin", help="Path to the binary database")
    parser.add_argument("--index", default="voice_sprites.bin.index.json", help="Path to the index JSON")
    parser.add_argument("--out", default="/storage/75D7-DC5F/speech_clip.mp4", help="Output MP4 file path")
    
    args = parser.parse_args()
    
    # Resolve relative paths in sandbox
    bin_path = args.bin
    index_path = args.index
    
    if not os.path.exists(bin_path) and os.path.exists("/root/token_synth_demo/voice_sprites.bin"):
        bin_path = "/root/token_synth_demo/voice_sprites.bin"
    if not os.path.exists(index_path) and os.path.exists("/root/token_synth_demo/voice_sprites.bin.index.json"):
        index_path = "/root/token_synth_demo/voice_sprites.bin.index.json"
        
    stitch_clip(args.sentence, bin_path, index_path, args.out)
