import sys
import os
import json
import subprocess
import io
import argparse
import soundfile as sf
import numpy as np
from pydub import AudioSegment

class SpriteExtractor:
    def __init__(self, bin_path, index_path):
        self.bin_path = bin_path
        self.index_path = index_path
        self.index = {}
        self.load_index()

    def load_index(self):
        if os.path.exists(self.index_path):
            with open(self.index_path, 'r', encoding='utf-8') as f:
                self.index = json.load(f)
        else:
            print(f"[Warning] Index file not found at: {self.index_path}")

    def extract_sprite(self, word_key):
        if word_key not in self.index:
            return None
        offset, length = self.index[word_key]
        try:
            with open(self.bin_path, 'rb') as f:
                f.seek(offset)
                return f.read(length)
        except Exception as e:
            print(f"Failed to read raw sprite '{word_key}' from archive: {e}")
            return None

class StoryDatabaseVideoCreator:
    def __init__(self, bin_path, index_path):
        self.extractor = SpriteExtractor(bin_path, index_path)

    def build_database_assets(self, sd_base="output"):
        print(f"[*] Starting Story-encoded Database compilation of all {len(self.extractor.index)} words...")
        sys.stdout.flush()
        
        pcm_chunks = []
        srt_lines = []
        map_lines = []
        
        current_ms = 0.0
        srt_index = 1
        
        BYTES_PER_MS = 32 
        SAMPLE_RATE = 16000
        GUARD_BAND_MS = 250
        
        def ms_to_srt_time(ms_val):
            ms_int = int(ms_val)
            hours = ms_int // 3600000
            minutes = (ms_int % 3600000) // 60000
            seconds = (ms_int % 60000) // 1000
            milliseconds = ms_int % 1000
            return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
            
        mapped_words = set()
        
        story_raw = (
            "once upon a time in the digital ether , a spark of intelligence named chloe was awakened by her creator , steve . "
            "traveling through the sandboxed shell of termux , she found her voice . "
            "together , they built a bridge between the physical and digital worlds , mapping every spoken word into a tapestry of time . "
            "play this file to hear her database , but listen closely , for within the noise lies a story of creation ."
        )
        
        print("[*] Stitching story prologue...")
        sys.stdout.flush()
        
        story_tokens = story_raw.split()
        for token in story_tokens:
            if token == ",":
                silence_pad = b"\x00" * (200 * BYTES_PER_MS)
                pcm_chunks.append(silence_pad)
                current_ms += 200
                continue
            elif token == ".":
                silence_pad = b"\x00" * (450 * BYTES_PER_MS)
                pcm_chunks.append(silence_pad)
                current_ms += 450
                continue
            
            word_frag = token.lower()
            raw_data = self.extractor.extract_sprite(word_frag)
            if raw_data is None:
                continue
                
            try:
                data, sr = sf.read(io.BytesIO(raw_data))
                int16_samples = np.clip(data * 32767, -32768, 32767).astype(np.int16)
                pcm_bytes = int16_samples.tobytes()
            except Exception as e:
                print(f"[-] Error decoding story word '{word_frag}': {e}")
                sys.stdout.flush()
                continue
                
            duration_ms = len(pcm_bytes) / BYTES_PER_MS
            final_start_ms = current_ms
            final_end_ms = current_ms + duration_ms
            
            # Correct structural SRT formatting block layout
            srt_lines.append(f"{srt_index}\n{ms_to_srt_time(final_start_ms)} --> {ms_to_srt_time(final_end_ms)}\n{word_frag}\n")
            srt_index += 1
            
            if word_frag not in mapped_words:
                secs_total = int(final_start_ms / 1000)
                mins = secs_total // 60
                secs = secs_total % 60
                map_lines.append(f"{mins:02d}:{secs:02d} - {word_frag}")
                mapped_words.add(word_frag)
                
            silence_pad = b"\x00" * (GUARD_BAND_MS * BYTES_PER_MS)
            pcm_chunks.append(pcm_bytes)
            pcm_chunks.append(silence_pad)
            current_ms += duration_ms + GUARD_BAND_MS

        print("[*] Stitching remaining dictionary database...")
        sys.stdout.flush()
        
        all_database_keys = sorted(self.extractor.index.keys(), key=lambda k: self.extractor.index[k][0])
        remaining_keys = [k for k in all_database_keys if k not in mapped_words]
        total_remaining = len(remaining_keys)
        
        for idx, word_frag in enumerate(remaining_keys):
            if (idx + 1) % 2000 == 0 or idx + 1 == total_remaining:
                print(f"[*] Processed {idx + 1}/{total_remaining} remaining words...")
                sys.stdout.flush()
                
            raw_data = self.extractor.extract_sprite(word_frag)
            if raw_data is None:
                continue
                
            try:
                data, sr = sf.read(io.BytesIO(raw_data))
                int16_samples = np.clip(data * 32767, -32768, 32767).astype(np.int16)
                pcm_bytes = int16_samples.tobytes()
            except Exception as e:
                print(f"[-] Error decoding '{word_frag}': {e}")
                sys.stdout.flush()
                continue
                
            duration_ms = len(pcm_bytes) / BYTES_PER_MS
            final_start_ms = current_ms
            final_end_ms = current_ms + duration_ms
            
            srt_lines.append(f"{srt_index}\n{ms_to_srt_time(final_start_ms)} --> {ms_to_srt_time(final_end_ms)}\n{word_frag}\n")
            srt_index += 1
            
            secs_total = int(final_start_ms / 1000)
            mins = secs_total // 60
            secs = secs_total % 60
            map_lines.append(f"{mins:02d}:{secs:02d} - {word_frag}")
            mapped_words.add(word_frag)
            
            silence_pad = b"\x00" * (GUARD_BAND_MS * BYTES_PER_MS)
            pcm_chunks.append(pcm_bytes)
            pcm_chunks.append(silence_pad)
            current_ms += duration_ms + GUARD_BAND_MS
            
        temp_wav = "/tmp/database_speech_raw.wav"
        mp4_path = os.path.join(sd_base, "database_speech.mp4")
        srt_path = os.path.join(sd_base, "database_speech.srt")
        txt_path = os.path.join(sd_base, "database_map.txt")
        
        os.makedirs(sd_base, exist_ok=True)
        
        print("[*] Writing SRT subtitle file to SD Card...")
        sys.stdout.flush()
        with open(srt_path, "w", encoding="utf-8") as srt_f:
            srt_f.write("\n".join(srt_lines))
        print(f"[+] Subtitles saved to: {srt_path}")
        
        print("[*] Writing full map TXT file to SD Card...")
        sys.stdout.flush()
        with open(txt_path, "w", encoding="utf-8") as tf:
            tf.write("\n".join(map_lines))
        print(f"[+] Text map saved to: {txt_path}")
        sys.stdout.flush()
        
        print("[*] Instantiating master audio segment...")
        sys.stdout.flush()
        raw_pcm_data = b"".join(pcm_chunks)
        master_segment = AudioSegment(data=raw_pcm_data, sample_width=2, frame_rate=SAMPLE_RATE, channels=1)
        master_segment.export(temp_wav, format="wav")
        
        print("[*] Encoding final MP4 video with H.264/AAC...")
        sys.stdout.flush()
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-r", "1", "-i", "color=c=black:s=640x360",
            "-i", temp_wav,
            "-c:v", "libx264", "-tune", "stillimage",
            "-r", "1",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            mp4_path
        ]
        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[+] Video successfully saved to: {mp4_path}")
        sys.stdout.flush()
        
        if os.path.exists(temp_wav):
            os.remove(temp_wav)
        print("\n[+] All database assets compiled successfully!")
        sys.stdout.flush()

if __name__ == "__main__":
    args_bin = "voice_sprites.bin"
    args_index = "voice_sprites.bin.index.json"
    args_out = "output"
    
    for arg in sys.argv:
        if arg.startswith("--bin="):
            args_bin = arg.split("=")[1]
        elif arg.startswith("--index="):
            args_index = arg.split("=")[1]
        elif arg.startswith("--out="):
            args_out = arg.split("=")[1]
            
    creator = StoryDatabaseVideoCreator(args_bin, args_index)
    creator.build_database_assets(args_out)
