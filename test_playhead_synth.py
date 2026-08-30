import sys
import os
import re
from pydub import AudioSegment

def parse_srt(srt_path):
    word_map = {}
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Matches: index \n start --> end \n word
    pattern = re.compile(r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.+)")
    matches = pattern.findall(content)
    
    def srt_time_to_ms(time_str):
        h, m, s_ms = time_str.split(":")
        s, ms = s_ms.split(",")
        return int(h)*3600000 + int(m)*60000 + int(s)*1000 + int(ms)
        
    for idx, start_str, end_str, word in matches:
        word = word.strip().lower()
        start_ms = srt_time_to_ms(start_str)
        end_ms = srt_time_to_ms(end_str)
        if word not in word_map:
            word_map[word] = (start_ms, end_ms - start_ms)
    return word_map

def synthesize_sentence(sentence, srt_path, mp4_path):
    print("[*] Loading coordinate map from SRT...")
    word_map = parse_srt(srt_path)
    
    print("[*] Loading master database audio from MP4...")
    master_audio = AudioSegment.from_file(mp4_path, format="mp4")
    
    words = sentence.lower().replace(",", "").replace(".", "").split()
    output_audio = AudioSegment.empty()
    
    print(f"[*] Stitching sentence: '{sentence}'")
    from pydub.silence import detect_nonsilent
    for w in words:
        if w in word_map:
            start_ms, duration_ms = word_map[w]
            print(f"  - Found '{w}': seek to {start_ms}ms, duration {duration_ms}ms")
            word_audio = master_audio[start_ms : start_ms + duration_ms]
            
            # Trim leading/trailing silence from the slice for crisp playback
            nonsilent_ranges = detect_nonsilent(word_audio, min_silence_len=50, silence_thresh=-35)
            if nonsilent_ranges:
                word_audio = word_audio[nonsilent_ranges[0][0] : nonsilent_ranges[-1][1]]
                
            output_audio += word_audio
            # Add a natural 35ms spacing
            output_audio += AudioSegment.silent(duration=35)
        else:
            print(f"  - Word '{w}' not found in database! Playing short beep.")
            from pydub.generators import Sine
            beep = Sine(440).to_audio_segment(duration=150).fade_out(10)
            output_audio += beep
            output_audio += AudioSegment.silent(duration=100)
            
    temp_out = "/tmp/playhead_proof.wav"
    output_audio.export(temp_out, format="wav")
    print(f"[+] Stitched audio exported to {temp_out}")
    
    # Play using host mpv player
    os.system("/system/bin/linker64 /data/data/com.termux/files/usr/bin/mpv --no-video " + temp_out + " > /dev/null 2>&1")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_playhead_synth.py '<sentence_to_speak>'")
        sys.exit(1)
        
    sentence = sys.argv[1]
    srt_path = "/storage/75D7-DC5F/database_speech.srt"
    mp4_path = "/storage/75D7-DC5F/database_speech.mp4"
    
    synthesize_sentence(sentence, srt_path, mp4_path)
