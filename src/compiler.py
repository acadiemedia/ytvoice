import sys
import os
import json
import subprocess
import io
import soundfile as sf
import numpy as np
from pydub import AudioSegment
from token_synth import TokenSynthEngine

class StoryDatabaseVideoCreator(TokenSynthEngine):
    def build_database_assets(self):
        # 1. Self-heal missing story words first
        missing_story_words = ["awakened", "sandboxed", "termux"]
        for word in missing_story_words:
            if word not in self.archiver.index:
                print(f"[*] Self-healing missing story word: '{word}'...")
                sys.stdout.flush()
                # Run piper to synthesize wav
                temp_wav_path = os.path.join(self.audio_sprites_dir, f"{word}.wav")
                model_path = "/root/en_US-amy-low.onnx"
                synthesis_text = self.pronunciation_overrides.get(word, word)
                cmd = ["piper", "--model", model_path, "--output_file", temp_wav_path]
                p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                p.communicate(input=f"{synthesis_text}\n".encode())
                
                # Pack it into the database
                self.archiver.pack_directory(self.audio_sprites_dir)
                if os.path.exists(temp_wav_path):
                    os.remove(temp_wav_path)
        
        print(f"[*] Starting Story-encoded Database compilation of all {len(self.archiver.index)} words...")
        sys.stdout.flush()
        
        pcm_chunks = []
        srt_lines = []
        map_lines = []
        
        current_ms = 0.0
        srt_index = 1
        
        # 16kHz, 16-bit, mono PCM = 32000 bytes/sec = 32 bytes/ms
        BYTES_PER_MS = 32 
        SAMPLE_RATE = 16000
        GUARD_BAND_MS = 250
        
        # Helper to format SRT timings
        def ms_to_srt_time(ms_val):
            ms_int = int(ms_val)
            hours = ms_int // 3600000
            minutes = (ms_int % 3600000) // 60000
            seconds = (ms_int % 60000) // 1000
            milliseconds = ms_int % 1000
            return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
            
        # Keep track of words we have mapped so we don't duplicate them in the tail
        mapped_words = set()
        
        # 2. Compile the Story Narratives
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
            # Handle punctuation pauses for natural story narration
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
            
            # Clean word
            word_frag = token.lower()
            raw_data = self.archiver.extract_sprite(word_frag)
            if raw_data is None:
                continue
                
            try:
                data, sr = sf.read(io.BytesIO(raw_data))
                int16_samples = (data * 32767).astype(np.int16)
                pcm_bytes = int16_samples.tobytes()
            except Exception as e:
                print(f"[-] Error decoding story word '{word_frag}': {e}")
                sys.stdout.flush()
                continue
                
            duration_ms = len(pcm_bytes) / BYTES_PER_MS
            final_start_ms = current_ms
            final_end_ms = current_ms + duration_ms
            
            # Write SRT entry
            srt_lines.append(f"{srt_index}")
            srt_lines.append(f"{ms_to_srt_time(final_start_ms)} --> {ms_to_srt_time(final_end_ms)}")
            srt_lines.append(f"{word_frag}\n")
            srt_index += 1
            
            # Write map entry (keep first occurrence in map)
            if word_frag not in mapped_words:
                secs_total = int(final_start_ms / 1000)
                mins = secs_total // 60
                secs = secs_total % 60
                map_lines.append(f"{mins:02d}:{secs:02d} - {word_frag}")
                mapped_words.add(word_frag)
                
            # Stitch with guard band
            silence_pad = b"\x00" * (GUARD_BAND_MS * BYTES_PER_MS)
            pcm_chunks.append(pcm_bytes)
            pcm_chunks.append(silence_pad)
            
            current_ms += duration_ms + GUARD_BAND_MS

        # 3. Compile the Remainder of the Database
        print("[*] Stitching remaining dictionary database...")
        sys.stdout.flush()
        
        all_database_keys = sorted(self.archiver.index.keys(), key=lambda k: self.archiver.index[k][0])
        remaining_keys = [k for k in all_database_keys if k not in mapped_words]
        
        total_remaining = len(remaining_keys)
        
        for idx, word_frag in enumerate(remaining_keys):
            if (idx + 1) % 2000 == 0 or idx + 1 == total_remaining:
                print(f"[*] Processed {idx + 1}/{total_remaining} remaining words...")
                sys.stdout.flush()
                
            raw_data = self.archiver.extract_sprite(word_frag)
            if raw_data is None:
                continue
                
            try:
                data, sr = sf.read(io.BytesIO(raw_data))
                int16_samples = (data * 32767).astype(np.int16)
                pcm_bytes = int16_samples.tobytes()
            except Exception as e:
                print(f"[-] Error decoding '{word_frag}': {e}")
                sys.stdout.flush()
                continue
                
            duration_ms = len(pcm_bytes) / BYTES_PER_MS
            final_start_ms = current_ms
            final_end_ms = current_ms + duration_ms
            
            # Write SRT entry
            srt_lines.append(f"{srt_index}")
            srt_lines.append(f"{ms_to_srt_time(final_start_ms)} --> {ms_to_srt_time(final_end_ms)}")
            srt_lines.append(f"{word_frag}\n")
            srt_index += 1
            
            # Write map entry
            secs_total = int(final_start_ms / 1000)
            mins = secs_total // 60
            secs = secs_total % 60
            map_lines.append(f"{mins:02d}:{secs:02d} - {word_frag}")
            mapped_words.add(word_frag)
            
            # Stitch with guard band
            silence_pad = b"\x00" * (GUARD_BAND_MS * BYTES_PER_MS)
            pcm_chunks.append(pcm_bytes)
            pcm_chunks.append(silence_pad)
            
            current_ms += duration_ms + GUARD_BAND_MS
            
        # Write SRT and text map files to SD card
        sd_base = "/storage/75D7-DC5F"
        temp_wav = "/tmp/database_speech_raw.wav"
        mp4_path = os.path.join(sd_base, "database_speech.mp4")
        srt_path = os.path.join(sd_base, "database_speech.srt")
        txt_path = os.path.join(sd_base, "database_map.txt")
        
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
        
        # Instantiate raw master segment from concatenated bytes
        print("[*] Instantiating master audio segment...")
        sys.stdout.flush()
        raw_pcm_data = b"".join(pcm_chunks)
        master_segment = AudioSegment(data=raw_pcm_data, sample_width=2, frame_rate=SAMPLE_RATE, channels=1)
        master_segment.export(temp_wav, format="wav")
        
        # Encode final MP4 video with H.264/AAC at 1 fps
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
        subprocess.run(ffmpeg_cmd, check=True)
        print(f"[+] Video successfully saved to: {mp4_path}")
        sys.stdout.flush()
        
        # Clean up temp files
        if os.path.exists(temp_wav):
            os.remove(temp_wav)
                
        print("\n[+] All database assets compiled successfully!")
        sys.stdout.flush()

if __name__ == "__main__":
    vocab_file = "/root/token_vocab.json"
    sprites_path = "/root/token_synth_demo/sprites"
    
    creator = StoryDatabaseVideoCreator(vocab_file, sprites_path)
    creator.build_database_assets()
