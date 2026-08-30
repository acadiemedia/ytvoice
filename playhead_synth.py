import sys
import os
import re
import argparse
import subprocess
import io
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

def get_youtube_audio_url(video_id_or_url):
    print(f"[*] Resolving YouTube direct stream URL for ID: {video_id_or_url}...")
    url = video_id_or_url
    if not url.startswith("http"):
        url = f"https://www.youtube.com/watch?v={video_id_or_url}"
    cmd = ["yt-dlp", "-g", "-f", "bestaudio", url]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    return result.stdout.strip()

def extract_remote_slice(stream_url, start_ms, duration_ms):
    start_sec = start_ms / 1000.0
    dur_sec = duration_ms / 1000.0
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start_sec:.3f}",
        "-t", f"{dur_sec:.3f}",
        "-i", stream_url,
        "-f", "wav",
        "-"
    ]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    wav_bytes, _ = p.communicate()
    return wav_bytes

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
        
    # 3. Pure Python fallback
    try:
        from pydub.playback import play
        segment = AudioSegment.from_file(file_path)
        play(segment)
    except Exception:
        print(f"[!] Could not play audio automatically. Output file saved at: {file_path}")

def synthesize_sentence(sentence, srt_path, audio_source, is_youtube=False):
    print(f"[*] Loading coordinate map from: {srt_path}")
    word_map = parse_srt(srt_path)
    
    stream_url = None
    master_audio = None
    
    if is_youtube:
        stream_url = get_youtube_audio_url(audio_source)
        if not stream_url:
            print("[Error] Failed to resolve YouTube audio stream URL.")
            sys.exit(1)
    else:
        print(f"[*] Loading master database audio from local file: {audio_source}")
        master_audio = AudioSegment.from_file(audio_source)
    
    words = sentence.lower().replace(",", "").replace(".", "").split()
    output_audio = AudioSegment.empty()
    
    print(f"[*] Stitching sentence: '{sentence}'")
    from pydub.silence import detect_nonsilent
    for w in words:
        if w in word_map:
            start_ms, duration_ms = word_map[w]
            print(f"  - Found '{w}': seek to {start_ms}ms, duration {duration_ms}ms")
            
            # Fetch slice either from remote YouTube stream or local file
            if is_youtube:
                wav_bytes = extract_remote_slice(stream_url, start_ms, duration_ms)
                if not wav_bytes:
                    print(f"    [!] Failed to stream '{w}' from YouTube")
                    continue
                word_audio = AudioSegment.from_file(io.BytesIO(wav_bytes), format="wav")
            else:
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
    parser = argparse.ArgumentParser(description="YTVoice Playhead Synthesizer")
    parser.add_argument("sentence", help="The sentence you want to synthesize")
    parser.add_argument("--srt", default="database_speech.srt", help="Path to the SRT subtitles file")
    parser.add_argument("--audio", default="database_speech.mp4", help="Path to the local video/audio database file")
    parser.add_argument("--youtube", help="YouTube Video ID or URL to stream from on-the-fly")
    
    args = parser.parse_args()
    
    srt_path = args.srt
    audio_source = args.audio
    is_youtube = False
    
    if args.youtube:
        audio_source = args.youtube
        is_youtube = True
    else:
        # Fallback to Termux SD card default path if not found in current directory
        if not os.path.exists(audio_source):
            sd_fallback = "/storage/75D7-DC5F/database_speech.mp4"
            if os.path.exists(sd_fallback):
                audio_source = sd_fallback
                
    if not os.path.exists(srt_path):
        sd_fallback = "/storage/75D7-DC5F/database_speech.srt"
        if os.path.exists(sd_fallback):
            srt_path = sd_fallback

    if not is_youtube and not os.path.exists(audio_source):
        print(f"[Error] Could not locate local MP4 file.")
        print(f"  Expected: {audio_source}")
        print("\nPlease specify a --youtube Video ID or place database_speech.mp4 locally.")
        sys.exit(1)
        
    if not os.path.exists(srt_path):
        print(f"[Error] Could not locate SRT file: {srt_path}")
        sys.exit(1)
        
    synthesize_sentence(args.sentence, srt_path, audio_source, is_youtube=is_youtube)
