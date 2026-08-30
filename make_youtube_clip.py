import sys
import os
import subprocess
from token_synth import TokenSynthEngine

class YouTubeClipEngine(TokenSynthEngine):
    def output_pcm(self, audio_segment, words, timings):
        # 1. Export the WAV
        temp_wav = "/tmp/synth_chunk.wav"
        audio_segment.export(temp_wav, format="wav")
        print(f"[+] Audio exported to {temp_wav}")

        # 2. Calculate timestamps for YouTube description
        print("\n--- YOUTUBE DESCRIPTION MAP ---")
        current_ms = 0
        
        # We only want to map actual words, not punctuation pauses or empty segments
        for idx, word in enumerate(words):
            # Format time in MM:SS
            seconds = int(current_ms / 1000)
            minutes = seconds // 60
            secs = seconds % 60
            timestamp_str = f"{minutes:02d}:{secs:02d}"
            
            # Print word with its timestamp
            # Only print actual word tokens, or clean up if it's punctuation
            if word not in [".", ",", "?", "!", ";", "-"]:
                print(f"{timestamp_str} - {word}")
                
            if idx < len(timings):
                current_ms += timings[idx]
        print("--------------------------------\n")

        # 3. Convert to MP4 and output to SD Card
        sd_card_path = "/storage/75D7-DC5F/speech_clip.mp4"
        print(f"[*] Packaging audio as MP4 video...")
        
        # Use ffmpeg to generate a black video track matching audio length
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=640x360",
            "-i", temp_wav,
            "-c:v", "libx264", "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            sd_card_path
        ]
        
        # Let's run the command
        subprocess.run(cmd, check=True)
        print(f"[+] Video successfully saved to: {sd_card_path}")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python3 make_youtube_clip.py <vocab_json> <sprites_dir> <text_to_speak>")
        sys.exit(1)

    vocab_file = sys.argv[1]
    sprites_path = sys.argv[2]
    text_input = sys.argv[3]
    
    # We parse words similar to how token_synth does it
    tokens = text_input.split()
    
    engine = YouTubeClipEngine(vocab_file, sprites_path)
    
    # Dynamically resolve tokens as done in token_synth
    resolved_tokens = []
    for t in tokens:
        clean_word = t.rstrip(".,?!;:").lower()
        punc = t[len(clean_word):]
        
        if clean_word:
            matched_id = None
            for key, word in engine.vocab.items():
                if word == clean_word:
                    matched_id = key
                    break
            if matched_id is None:
                max_key = max(int(k) for k in engine.vocab.keys() if k.isdigit())
                new_id = str(max_key + 1)
                engine.vocab[new_id] = clean_word
                matched_id = new_id
            resolved_tokens.append(matched_id)
        
        if punc:
            for char in punc:
                resolved_tokens.append(char)
                
    engine.play_token_stream(resolved_tokens)
