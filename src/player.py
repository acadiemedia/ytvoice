import sys
import os
import re
import tempfile
import shutil
import argparse
import subprocess
import io
import string
import glob
import warnings
from ffmpeg_util import get_ffmpeg_exe, configure_pydub

with warnings.catch_warnings():
    warnings.simplefilter("ignore", RuntimeWarning)
    from pydub import AudioSegment

configure_pydub()

FFMPEG_EXE = get_ffmpeg_exe()

# --- IMA ADPCM decode tables (standard) ---
IMA_INDEX_STEP = (-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8)
IMA_STEP = (7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31,
            34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143,
            157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544,
            598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878,
            2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894,
            6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818,
            18500, 20350, 22385, 24623, 27086, 29794, 32767)

def decode_ima_adpcm(raw, block_align=1024):
    """
    Decode an IMA ADPCM sprite (WAV audio format 17) to raw 16-bit mono PCM
    without any third-party dependency. Each block carries a 4-byte header
    (int16 predictor, int8 step index, int8 reserved) followed by 4-bit nibbles.
    """
    data_start = None
    data_end = 0
    pos = 12
    while pos + 8 <= len(raw):
        cid = raw[pos:pos+4]
        sz = int.from_bytes(raw[pos+4:pos+8], 'little')
        if cid == b'data':
            data_start = pos + 8
            data_end = data_start + sz
            break
        pos += 8 + sz + (sz % 2)
    if data_start is None:
        return b""
    payload = raw[data_start:data_end]

    out = []
    idx = 0
    for blk_start in range(0, len(payload) - 4, block_align):
        blk = payload[blk_start:blk_start + block_align]
        pred = int.from_bytes(blk[0:2], 'little', signed=True)
        idx = blk[2]
        out.append(pred)
        for byte in blk[4:]:
            low = byte & 0x0F
            high = byte >> 4
            for nib in (low, high):
                step = IMA_STEP[idx]
                diff = (step >> 3)
                if nib & 1:
                    diff += (step >> 2)
                if nib & 2:
                    diff += (step >> 1)
                if nib & 4:
                    diff += step
                pred = pred - diff if (nib & 8) else pred + diff
                if pred > 32767:
                    pred = 32767
                elif pred < -32768:
                    pred = -32768
                idx = max(0, min(88, idx + IMA_INDEX_STEP[nib]))
                out.append(pred)
    return b''.join(v.to_bytes(2, 'little', signed=True) for v in out)


class SpriteExtractor:
    def __init__(self, bin_path, index_path):
        self.bin_path = bin_path
        self.index_path = index_path
        self.index = {}
        self.load_index()

    def load_index(self):
        import json
        if os.path.exists(self.index_path):
            with open(self.index_path, 'r', encoding='utf-8') as f:
                self.index = json.load(f)

    def extract_sprite(self, word_key):
        if word_key not in self.index:
            return None
        offset, length = self.index[word_key]
        try:
            with open(self.bin_path, 'rb') as f:
                f.seek(offset)
                return f.read(length)
        except Exception:
            return None

def parse_srt(srt_path_or_content):
    word_map = {}
    content = ""
    
    if srt_path_or_content and os.path.exists(srt_path_or_content):
        with open(srt_path_or_content, "r", encoding="utf-8") as f:
            content = f.read()
    elif srt_path_or_content:
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

class PhraseMatcher:
    """
    Greedy longest-phrase matching against a phrase database (phrase_db.json)
    built by tools/add_youtube_phrases.py. Phrases win over word sprites; the
    player falls back to word segmentation for anything un-phrased.
    """
    def __init__(self, db_path):
        self.db_path = db_path
        self.phrases = {}  # normalized key -> list of candidate dicts
        self.max_len = 0
        self.load(db_path)

    def load(self, db_path):
        import json
        if not db_path or not os.path.exists(db_path):
            return
        with open(db_path, "r", encoding="utf-8") as f:
            db = json.load(f)
        for key, candidates in db.items():
            norm = key.strip().lower()
            if norm and candidates:
                self.phrases[norm] = candidates
                wc = len(norm.split())
                if wc > self.max_len:
                    self.max_len = wc

    def find_longest(self, words, start_idx):
        """Return (key, word_count, candidates) for the longest phrase starting
        at start_idx, or None if no phrase starts there."""
        max_try = min(self.max_len, len(words) - start_idx)
        for count in range(max_try, 0, -1):
            key = " ".join(words[start_idx:start_idx + count])
            cands = self.phrases.get(key)
            if cands:
                return key, count, cands
        return None

def fetch_youtube_subtitles(video_id_or_url):
    print(f"[*] Fetching subtitles directly from YouTube: {video_id_or_url}...")
    url = video_id_or_url
    if not url.startswith("http"):
        url = f"https://youtube.com/watch?v={video_id_or_url}"
        
    temp_prefix = os.path.join(tempfile.gettempdir(), f"yt_subs_{video_id_or_url.replace('-', '_')}")
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

def extract_audio_slice(source_path_or_url, start_ms, duration_ms, normalize=False):
    """
    Slices a small segment of audio from a local file or remote URL on-the-fly
    using ffmpeg range seeks, keeping memory overhead minimal.
    When normalize=True the segment is resampled to 16kHz mono so clips from
    different videos mix at a consistent sample rate with the sprite DB.
    """
    start_sec = start_ms / 1000.0
    dur_sec = duration_ms / 1000.0
    cmd = [
        FFMPEG_EXE, "-y",
        "-ss", f"{start_sec:.3f}",
        "-t", f"{dur_sec:.3f}",
        "-i", source_path_or_url,
    ]
    if normalize:
        cmd += ["-ar", "16000", "-ac", "1"]
    cmd += ["-f", "wav", "-"]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        wav_bytes, _ = p.communicate()
        return wav_bytes
    except FileNotFoundError:
        return b""

def normalize_loudness(segment, target_dbfs=-18.0, max_gain_db=12.0):
    """
    Bring a decoded clip toward a target average loudness so phrases sliced
    from different videos don't jump wildly in volume.
    """
    try:
        loudness = segment.dBFS
        if loudness == float("-inf"):
            return segment
        gain_db = target_dbfs - loudness
        gain_db = max(-max_gain_db, min(gain_db, max_gain_db))
        return segment.apply_gain(gain_db)
    except Exception:
        return segment

def _try_play(cmd):
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False

def play_audio(file_path):
    if os.path.exists("/system/bin/linker64"):
        termux_mpv = "/data/data/com.termux/files/usr/bin/mpv"
        if os.path.exists(termux_mpv):
            os.system(f"/system/bin/linker64 {termux_mpv} --no-video {file_path} > /dev/null 2>&1")
            return

    mpv = shutil.which("mpv")
    if mpv and _try_play([mpv, "--no-video", file_path]):
        return

    ffplay = shutil.which("ffplay")
    if ffplay and _try_play([ffplay, "-nodisp", "-autoexit", file_path]):
        return

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            from pydub.playback import play
        segment = AudioSegment.from_file(file_path)
        play(segment)
        return
    except Exception:
        pass

    if sys.platform == "win32":
        try:
            import winsound
            winsound.PlaySound(file_path, winsound.SND_FILENAME)
            return
        except Exception:
            pass

    print(f"[!] Could not play audio automatically. Output file saved at: {file_path}")

def _phrase_tokenize(text):
    """Tokenize sentence text exactly like tools/add_youtube_phrases.py so
    phrase keys line up with the phrase DB (punctuation -> space, apostrophes
    kept)."""
    import re as _re
    return _re.sub(r"[^0-9a-z\s']", " ", text.lower()).split()


def synthesize_sentence(sentence, srt_source, audio_source, is_youtube=False, cache_dir=None, bin_source=None, index_source=None, phrase_db_path=None, no_play=False):
    word_map = {}
    extractor = None
    matcher = None
    
    if phrase_db_path and os.path.exists(phrase_db_path):
        print(f"[*] Booting phrase database mode: {phrase_db_path}")
        matcher = PhraseMatcher(phrase_db_path)
        if not matcher.phrases:
            print("[!] phrase_db.json present but empty; continuing with word sprites only.")
            matcher = None
    
    if bin_source and index_source:
        print(f"[*] Booting local binary database mode (direct byte seeks): {bin_source}")
        extractor = SpriteExtractor(bin_source, index_source)
        word_map = {k: (0, 0) for k in extractor.index.keys()}
    else:
        word_map = parse_srt(srt_source)
        
    if not word_map:
        print("[Error] Subtitle map is empty or could not be parsed.")
        sys.exit(1)
        
    stream_url = None
    video_stream_urls = {}  # video_id -> resolved stream URL (phrases)
    
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
    
    tokens = _phrase_tokenize(sentence)
    output_audio = AudioSegment.empty()
    
    # Build a plan: phrases win greedily; leftover words go to the word pipeline.
    plan = []
    i = 0
    while i < len(tokens):
        if matcher:
            hit = matcher.find_longest(tokens, i)
            if hit:
                key, count, cands = hit
                plan.append(("phrase", key, cands))
                i += count
                continue
        plan.append(("word", tokens[i]))
        i += 1

    print(f"[*] Stitching sentence: '{sentence}'")
    from pydub.silence import detect_nonsilent
    
    pi = 0
    while pi < len(plan):
        item = plan[pi]
        kind = item[0]
        if kind == "phrase":
            key, cands = item[1], item[2]
            phrase_audio = None
            for cand in cands:
                video_id = cand.get("video_id")
                start_ms = cand.get("start_ms", 0)
                end_ms = cand.get("end_ms", start_ms)
                duration_ms = max(1, end_ms - start_ms)
                cache_file = None
                if cache_dir and video_id:
                    cache_file = os.path.join(cache_dir, "phrases",
                                              f"{video_id}_{start_ms}_{end_ms}.wav")
                    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
                    if os.path.exists(cache_file):
                        print(f"  - [Phrase Cache Hit] '{key}' ({video_id})")
                        try:
                            phrase_audio = AudioSegment.from_file(cache_file, format="wav")
                            break
                        except Exception:
                            phrase_audio = None
                if phrase_audio is not None:
                    break
                if not video_id:
                    continue
                try:
                    if video_id not in video_stream_urls:
                        video_stream_urls[video_id] = get_youtube_audio_url(video_id)
                    url = video_stream_urls.get(video_id)
                    if not url:
                        continue
                    wav_bytes = extract_audio_slice(url, start_ms, duration_ms, normalize=True)
                    if not wav_bytes:
                        print(f"    [!] Failed to slice '{key}' from {video_id}")
                        continue
                    phrase_audio = AudioSegment.from_file(io.BytesIO(wav_bytes), format="wav")
                    if cache_file:
                        try:
                            phrase_audio.export(cache_file, format="wav")
                        except Exception:
                            pass
                    break
                except Exception as e:
                    print(f"    [!] Phrase '{key}' from {video_id} failed: {e}")
                    phrase_audio = None
                    continue
            if phrase_audio is None:
                print(f"  - Phrase '{key}' had no usable candidates; falling back to word sprites.")
                for w in key.split():
                    plan.insert(pi + 1, ("word", w))
                pi += 1
                continue
            # Normalize loudness so clips from different videos don't jump.
            phrase_audio = normalize_loudness(phrase_audio)
            nonsilent_ranges = detect_nonsilent(phrase_audio, min_silence_len=50, silence_thresh=-50)
            if nonsilent_ranges:
                phrase_audio = phrase_audio[nonsilent_ranges[0][0] : nonsilent_ranges[-1][1]]
            output_audio += phrase_audio
            output_audio += AudioSegment.silent(duration=35)
            print(f"  - Phrase matched: '{key}' ({len(cands)} candidates)")
            pi += 1
            continue
        
        # "word" item: existing word pipeline.
        w = item[1]
        segments = segment_word(w, word_map)
        if segments:
            for seg in segments:
                # Check cache
                cached_path = None
                if cache_dir:
                    cached_path = os.path.join(cache_dir, f"{seg}.wav")
                    
                if cached_path and os.path.exists(cached_path):
                    print(f"  - [Cache Hit] '{seg}' loaded locally.")
                    word_audio = AudioSegment.from_file(cached_path, format="wav")
                else:
                    if extractor:
                        raw_data = extractor.extract_sprite(seg)
                        if not raw_data:
                            print(f"    [!] Failed to extract '{seg}' from binary database")
                            continue
                        try:
                            pcm_bytes = decode_ima_adpcm(raw_data)
                            word_audio = AudioSegment(data=pcm_bytes, sample_width=2, frame_rate=16000, channels=1)
                        except Exception as e:
                            print(f"    [-] Error decoding '{seg}' from binary database: {e}")
                            continue
                    else:
                        start_ms, duration_ms = word_map[seg]
                        print(f"  - Found '{seg}': seek to {start_ms}ms, duration {duration_ms}ms")
                        if is_youtube:
                            # Lazy resolve URL on-demand
                            if not stream_url:
                                stream_url = get_youtube_audio_url(audio_source)
                                if not stream_url:
                                    print("[Error] Failed to resolve YouTube audio stream URL.")
                                    sys.exit(1)
                            wav_bytes = extract_audio_slice(stream_url, start_ms, duration_ms)
                        else:
                            # Slice local media file on-the-fly
                            wav_bytes = extract_audio_slice(audio_source, start_ms, duration_ms)
                            
                        if not wav_bytes:
                            print(f"    [!] Failed to extract '{seg}'")
                            continue
                        word_audio = AudioSegment.from_file(io.BytesIO(wav_bytes), format="wav")
                    
                    # Save to local cache dir
                    if cached_path:
                        try:
                            word_audio.export(cached_path, format="wav")
                            print(f"    [+] Cached '{seg}' -> {cached_path}")
                        except Exception:
                            pass
                
                # Trim leading/trailing silence from the slice for crisp playback.
                # Use a low threshold (-50 dBFS) so quiet final fricatives (/f/, /s/,
                # /th/) are preserved instead of being mistaken for silence.
                nonsilent_ranges = detect_nonsilent(word_audio, min_silence_len=50, silence_thresh=-50)
                if nonsilent_ranges:
                    word_audio = word_audio[nonsilent_ranges[0][0] : nonsilent_ranges[-1][1]]
                    
                output_audio += word_audio
                output_audio += AudioSegment.silent(duration=35)
            pi += 1
        else:
            print(f"  - Word '{w}' not found in database! Playing short beep.")
            from pydub.generators import Sine
            beep = Sine(440).to_audio_segment(duration=150).fade_out(10)
            output_audio += beep
            output_audio += AudioSegment.silent(duration=100)
            pi += 1
            
    temp_out = os.path.join(tempfile.gettempdir(), "playhead_proof.wav")
    output_audio.export(temp_out, format="wav")
    print(f"[+] Stitched audio exported to {temp_out}")
    if not no_play:
        play_audio(temp_out)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YTVoice Playhead Synthesizer")
    parser.add_argument("sentence", nargs="?", help="The sentence you want to synthesize")
    parser.add_argument("--srt", default="database_speech.srt", help="Path to the local SRT subtitles file")
    parser.add_argument("--audio", default="database_speech.mp4", help="Path to the local video/audio database file")
    parser.add_argument("--youtube", nargs="?", const="r-WQt6Hi86Y", help="YouTube Video ID or URL to stream from on-the-fly")
    parser.add_argument("--cache-dir", default=".yt_cache", help="Directory to cache fetched audio slices")
    parser.add_argument("--bin", help="Path to the binary database file (e.g. voice_sprites.bin)")
    parser.add_argument("--index", help="Path to the JSON index file (e.g. voice_sprites.bin.index.json)")
    parser.add_argument("--download", help="Bootstrap and download both SRT and MP4 master files locally from a YouTube ID/URL for offline use")
    parser.add_argument("--phrase-db", default="phrase_db.json", help="Path to the phrase database (from tools/add_youtube_phrases.py)")
    parser.add_argument("--no-play", action="store_true", help="Export audio without playing it")
    
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
    
    # Decide binary mode
    is_binary_mode = False
    bin_source = args.bin
    index_source = args.index
    
    # If --bin was explicitly passed, honor it (must not fall through to YouTube).
    # --index defaults to voice_sprites.bin.index.json when --bin is given.
    if args.bin:
        is_binary_mode = True
        if not index_source:
            index_source = "voice_sprites.bin.index.json"
    elif not is_youtube:
        # Auto-detect binary mode in current directory if no specific sources are passed
        default_bin = "voice_sprites.bin"
        default_index = "voice_sprites.bin.index.json"
        if os.path.exists(default_bin) and os.path.exists(default_index):
            is_binary_mode = True
            bin_source = default_bin
            index_source = default_index
            
    # Auto-detect local MP4 mode
    if not is_youtube and not is_binary_mode and not os.path.exists(audio_source):
        # Zero-Config fallback: if no local database assets are found, default to YouTube cloud mode
        print("[*] No local database assets found. Defaulting to YouTube cloud streaming mode...")
        is_youtube = True
        args.youtube = "r-WQt6Hi86Y"
            
    if is_youtube:
        youtube_id = args.youtube if args.youtube else "r-WQt6Hi86Y"
        audio_source = youtube_id
        # Fetch subtitles from YouTube if local default SRT is missing
        if srt_source == "database_speech.srt" and not os.path.exists(srt_source):
            print(f"[*] No local SRT found. Fetching subtitles from video...")
            remote_srt = fetch_youtube_subtitles(youtube_id)
            if remote_srt:
                srt_source = remote_srt
    else:
        if not is_binary_mode and not os.path.exists(audio_source):
            sd_fallback = "/storage/75D7-DC5F/database_speech.mp4"
            if os.path.exists(sd_fallback):
                audio_source = sd_fallback
                
    # Local SRT fallback checks (only if not in binary mode)
    if not is_binary_mode and isinstance(srt_source, str) and not os.path.exists(srt_source):
        sd_fallback = "/storage/75D7-DC5F/database_speech.srt"
        if os.path.exists(sd_fallback):
            srt_source = sd_fallback
        else:
            local_fallback = "database_speech.srt"
            if os.path.exists(local_fallback):
                srt_source = local_fallback

    if not is_youtube and not is_binary_mode and not os.path.exists(audio_source):
        print(f"[Error] Could not locate local MP4 file: {audio_source}")
        sys.exit(1)
        
    if not is_binary_mode and isinstance(srt_source, str) and not os.path.exists(srt_source):
        print(f"[Error] Could not locate local or remote SRT source.")
        sys.exit(1)
        
    synthesize_sentence(args.sentence, srt_source, audio_source, 
                        is_youtube=is_youtube, 
                        cache_dir=args.cache_dir,
                        bin_source=bin_source,
                        index_source=index_source,
                        phrase_db_path=args.phrase_db,
                        no_play=args.no_play)
