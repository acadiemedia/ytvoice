import sys
import os
import re
import argparse
import subprocess
import io
import string
import glob
from pydub import AudioSegment

def parse_srt(srt_path_or_content):
    word_map = {}
    content = ""
    
    if os.path.exists(srt_path_or_content):
        with open(srt_path_or_content, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = srt_path_or_content
        
    if not content:
        return word_map
    
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

def segment_word(word, word_map):
    """
    Greedy recursive prefix matching to segment an unknown word into
    known sub-word pieces existing in the database (e.g., 'haba' -> 'ha' + 'ba').
    """
    if not word:
        return []
    if word in word_map:
        return [word]
        
    # Attempt to find the longest matching prefix
    for i in range(len(word), 0, -1):
        prefix = word[:i]
        if prefix in word_map:
            suffix = word[i:]
            if not suffix:
                return [prefix]
            suffix_segments = segment_word(suffix, word_map)
            if suffix_segments is not None:
                return [prefix] + suffix_segments
    return None

def fetch_youtube_subtitles(video_id_or_url):
    print(f"[*] Fetching subtitles directly from YouTube: {video_id_or_url}...")
    url = video_id_or_url
    if not url.startswith("http"):
        url = f"https://youtube.com/watch?v={video_id_or_url}"
        
    temp_prefix = os.path.join(os.environ.get("TMPDIR", "/tmp"), f"yt_subs_{video_id_or_url.replace('-', '_')}")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--write-subs", "--sub-langs", "en.*,en",
        "--skip-download", "--convert-subs", "srt",
        "-o", temp_prefix,
        url
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True)
        srt_files = glob.glob(f"{temp_prefix}.*.srt")
        if srt_files:
            srt_file = srt_files[0]
            with open(srt_file, "r", encoding="utf-8") as f:
                content = f.read()
            os.remove(srt_file) # Clean up
            return content
    except Exception:
        pass
    return None

def download_database_assets(video_id_or_url):
    print(f"[*] Bootstrapping offline database assets from video: {video_id_or_url}...")
    url = video_id_or_url
    if not url.startswith("http"):
        url = f"https://youtube.com/watch?v={video_id_or_url}"
        
    # 1. Download subtitles
    print("[*] Downloading subtitles...")
    srt_content = fetch_youtube_subtitles(video_id_or_url)
    if srt_content:
        with open("database_speech.srt", "w", encoding="utf-8") as f:
            f.write(srt_content)
        print("[+] Subtitles saved locally to: database_speech.srt")
    else:
        print("[!] Warning: Could not retrieve subtitles from YouTube.")
        
    # 2. Download full audio file
    print("[*] Downloading master audio database (this may take a moment)...")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "bestaudio",
        "-o", "database_speech.%(ext)s",
        url
    ]
    try:
        subprocess.run(cmd, check=True)
        # Find the downloaded file
        downloaded_files = glob.glob("database_speech.*")
        audio_files = [f for f in downloaded_files if not f.endswith(".srt")]
        if audio_files:
            src_file = audio_files[0]
            if src_file != "database_speech.mp4":
                if os.path.exists("database_speech.mp4"):
                    os.remove("database_speech.mp4")
                os.rename(src_file, "database_speech.mp4")
            print("[+] Master audio database saved locally to: database_speech.mp4")
            print("[+] Bootstrap complete! You can now run completely offline.")
        else:
            print("[!] Error: No audio file was downloaded.")
    except Exception as e:
        print(f"[!] Error downloading master audio: {e}")

def get_youtube_audio_url(video_id_or_url):
    print(f"[*] Resolving YouTube direct stream URL for ID: {video_id_or_url}...")
    url = video_id_or_url
    if not url.startswith("http"):
        url = f"https://youtube.com/watch?v={video_id_or_url}"
    cmd = [sys.executable, "-m", "yt_dlp", "-g", "-f", "bestaudio", url]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return result.stdout.strip()
    except FileNotFoundError:
        print("[!] Execution error: ensure 'yt-dlp' is properly installed and added to PATH.")
        return None
    except subprocess.CalledProcessError as e:
        print(f"[!] yt-dlp error: Failed to retrieve video stream. {e.stderr.strip()}")
        return None

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
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        wav_bytes, _ = p.communicate()
        return wav_bytes
    except FileNotFoundError:
        return b""

def play_audio(file_path):
    if os.path.exists("/system/bin/linker64"):
        termux_mpv = "/data/data/com.termux/files/usr/bin/mpv"
        if os.path.exists(termux_mpv):
            os.system(f"/system/bin/linker64 {termux_mpv} --no-video {file_path} > /dev/null 2>&1")
            return
            
    if os.system(f"mpv --no-video {file_path} > /dev/null 2>&1") == 0:
        return
    if os.system(f"ffplay -nodisp -autoexit {file_path} > /dev/null 2>&1") == 0:
        return
        
    try:
        from pydub.playback import play
        segment = AudioSegment.from_file(file_path)
        play(segment)
    except Exception:
        print(f"[!] Could not play audio automatically. Output file saved at: {file_path}")

def synthesize_sentence(sentence, srt_source, audio_source, is_youtube=False, cache_dir=None):
    word_map = parse_srt(srt_source)
    if not word_map:
        print("[Error] Subtitle map is empty or could not be parsed.")
        sys.exit(1)
        
    stream_url = None
    master_audio = None
    
    if is_youtube and cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        
    if not is_youtube:
        print(f"[*] Loading master database audio from local file: {audio_source}")
        master_audio = AudioSegment.from_file(audio_source)
    
    # Secure punctuation cleansing pattern
    clean_sentence = sentence.translate(str.maketrans('', '', string.punctuation))
    words = clean_sentence.lower().split()
    output_audio = AudioSegment.empty()
    
    # Expand composite/unknown words into sub-word tokens
    processed_words = []
    for w in words:
        segments = segment_word(w, word_map)
        if segments:
            for seg in segments:
                processed_words.append((seg, True))
        else:
            processed_words.append((w, False))
            
    print(f"[*] Stitching sentence: '{sentence}'")
    from pydub.silence import detect_nonsilent
    for w, is_found in processed_words:
        if is_found:
            start_ms, duration_ms = word_map[w]
            
            # Check cache in YouTube mode
            cached_path = None
            if is_youtube and cache_dir:
                cached_path = os.path.join(cache_dir, f"{w}.wav")
                
            if cached_path and os.path.exists(cached_path):
                print(f"  - [Cache Hit] '{w}' loaded locally.")
                word_audio = AudioSegment.from_file(cached_path, format="wav")
            else:
                print(f"  - Found '{w}': seek to {start_ms}ms, duration {duration_ms}ms")
                if is_youtube:
                    # Lazy resolve URL on-demand
                    if not stream_url:
                        stream_url = get_youtube_audio_url(audio_source)
                        if not stream_url:
                            print("[Error] Failed to resolve YouTube audio stream URL.")
                            sys.exit(1)
                            
                    wav_bytes = extract_remote_slice(stream_url, start_ms, duration_ms)
                    if not wav_bytes:
                        print(f"    [!] Failed to stream '{w}' from YouTube")
                        continue
                    word_audio = AudioSegment.from_file(io.BytesIO(wav_bytes), format="wav")
                    
                    # Save to local cache dir
                    if cached_path:
                        try:
                            word_audio.export(cached_path, format="wav")
                            print(f"    [+] Cached '{w}' -> {cached_path}")
                        except Exception:
                            pass
                else:
                    word_audio = master_audio[start_ms : start_ms + duration_ms]
            
            # Trim leading/trailing silence from the slice for crisp playback
            nonsilent_ranges = detect_nonsilent(word_audio, min_silence_len=50, silence_thresh=-35)
            if nonsilent_ranges:
                word_audio = word_audio[nonsilent_ranges[0][0] : nonsilent_ranges[-1][1]]
                
            output_audio += word_audio
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
    play_audio(temp_out)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YTVoice Playhead Synthesizer")
    parser.add_argument("sentence", nargs="?", help="The sentence you want to synthesize")
    parser.add_argument("--srt", help="Path to the local SRT subtitles file")
    parser.add_argument("--audio", default="database_speech.mp4", help="Path to the local video/audio database file")
    parser.add_argument("--youtube", help="YouTube Video ID or URL to stream from on-the-fly")
    parser.add_argument("--cache-dir", default=".yt_cache", help="Directory to cache fetched audio slices (YouTube mode only)")
    parser.add_argument("--download", help="Bootstrap and download both SRT and MP4 master files locally from a YouTube ID/URL for offline use")
    
    args = parser.parse_args()
    
    # Handle bootstrap action
    if args.download:
        download_database_assets(args.download)
        sys.exit(0)
        
    if not args.sentence:
        parser.print_help()
        sys.exit(1)
        
    srt_source = args.srt
    audio_source = args.audio
    is_youtube = bool(args.youtube)
    
    if is_youtube:
        audio_source = args.youtube
        # Fetch subtitles from YouTube if local SRT path was not provided
        if not srt_source:
            print(f"[*] No local SRT provided. Fetching subtitles from video...")
            srt_source = fetch_youtube_subtitles(args.youtube)
            if not srt_source:
                print("[*] No custom subtitles found on YouTube video. Falling back to local default search.")
                srt_source = "database_speech.srt"
    else:
        if not os.path.exists(audio_source):
            sd_fallback = "/storage/75D7-DC5F/database_speech.mp4"
            if os.path.exists(sd_fallback):
                audio_source = sd_fallback
                
    # Local SRT fallback checks
    if isinstance(srt_source, str) and not os.path.exists(srt_source):
        sd_fallback = "/storage/75D7-DC5F/database_speech.srt"
        if os.path.exists(sd_fallback):
            srt_source = sd_fallback
        else:
            local_fallback = "database_speech.srt"
            if os.path.exists(local_fallback):
                srt_source = local_fallback

    if not is_youtube and not os.path.exists(audio_source):
        print(f"[Error] Could not locate local MP4 file: {audio_source}")
        sys.exit(1)
        
    if isinstance(srt_source, str) and not os.path.exists(srt_source):
        print(f"[Error] Could not locate local or remote SRT source.")
        sys.exit(1)
        
    synthesize_sentence(args.sentence, srt_source, audio_source, is_youtube=is_youtube, cache_dir=args.cache_dir)
