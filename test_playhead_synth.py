import sys
import os
import re
import argparse
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

def play_audio(file_path):
    # 1. Android Termux PRoot environment check
    if os.path.exists("/system/bin/linker64"):
        termux_mpv = "/data/data/com.termux/files/usr/bin/mpv"
        if os.path.exists(termux_mpv):
            os.system(f"/system/bin/linker64 {termux_mpv} --no-video {file_path} > /dev/null 2>&1")
            return
            
    # 2. Cross-platform command fallbacks (Mac/Linux/Windows)
    if os.system(f"mpv --no-video {file_path} > /dev/null 2>&1") == 0:
        return
    if os.system(f"ffplay -nodisp -autoexit {file_path} > /dev/null 2>&1") == 0:
        return
        
    # 3. Pure Python fallback (requires simpleaudio or pyaudio)
    try:
        from pydub.playback import play
        segment = AudioSegment.from_file(file_path)
        play(segment)
    except Exception:
        print(f"[!] Could not play audio automatically. Output file saved at: {file_path}")

def synthesize_sentence(sentence, srt_path, mp4_path):
    print(f"[*] Loading coordinate map from: {srt_path}")
    word_map = parse_srt(srt_path)
    
    print(f"[*] Loading master database audio from: {mp4_path}")
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
            
    temp_out = os.path.join(os.environ.get("TMPDIR", "/tmp"), "playhead_proof.wav")
    output_audio.export(temp_out, format="wav")
    print(f"[+] Stitched audio exported to {temp_out}")
    
    # Play the output
    play_audio(temp_out)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YTVoice Playhead Synthesizer Proof of Concept")
    parser.add_argument("sentence", help="The sentence you want to synthesize")
    parser.add_argument("--srt", default="database_speech.srt", help="Path to the SRT subtitles file")
    parser.add_argument("--audio", default="database_speech.mp4", help="Path to the video/audio database file")
    
    args = parser.parse_args()
    
    srt_path = args.srt
    mp4_path = args.audio
    
    # Fallback to Termux SD card default path if not found in current directory
    if not os.path.exists(srt_path):
        sd_fallback = "/storage/75D7-DC5F/database_speech.srt"
        if os.path.exists(sd_fallback):
            srt_path = sd_fallback
            
    if not os.path.exists(mp4_path):
        sd_fallback = "/storage/75D7-DC5F/database_speech.mp4"
        if os.path.exists(sd_fallback):
            mp4_path = sd_fallback

    if not os.path.exists(srt_path) or not os.path.exists(mp4_path):
        print(f"[Error] Could not locate SRT or MP4 files.")
        print(f"  Expected SRT: {srt_path}")
        print(f"  Expected MP4: {mp4_path}")
        print("\nPlease place database_speech.srt and database_speech.mp4 in this folder or specify their locations with --srt and --audio.")
        sys.exit(1)
        
    synthesize_sentence(args.sentence, srt_path, mp4_path)
