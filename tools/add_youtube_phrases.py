#!/usr/bin/env python3
"""
Build a phrase database (phrase_db.json) by searching YouTube, downloading each
video's English captions, and locating exact phrase occurrences in the caption
timeline (YouTube auto-captions carry per-word inline timestamps).

For a requested phrase we store a list of candidate slices:

    {
      "phrase": [
        {"video_id": "abc123", "title": "...", "start_ms": 1200,
         "end_ms": 3200, "duration_ms": 2000, "track": "auto|manual"}
      ]
    }

The player (src/player.py --phrases) greedily matches the longest known phrase,
slices the matching candidate's audio on-the-fly, and falls back to word
sprites for anything un-phrased. No audio is downloaded at build time.

Usage:
    python tools/add_youtube_phrases.py "life is what happens" --commit
    python tools/add_youtube_phrases.py --sentence "life is what happens when you are busy" --min-words 3 --max-words 5 --commit
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

# How long a gap between two spoken words may be before we treat the words as
# belonging to different speech segments (blocks phrase matching across them).
MAX_WORD_GAP_MS = 1500

DEFAULT_RESULTS = 8
DEFAULT_MAX_CANDIDATES = 6


# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------
def normalize_words(text):
    """Lowercase, strip punctuation, and tokenize into plain words."""
    text = text.lower()
    text = re.sub(r"[^0-9a-z\s']", " ", text)
    return text.split()


def words_to_key(words):
    return " ".join(words)


# ---------------------------------------------------------------------------
# WebVTT timestamped caption parsing
# ---------------------------------------------------------------------------
def _ts_parse(ts):
    """Parse 'HH:MM:SS.mmm' (or 'MM:SS.mmm') into milliseconds."""
    main, _, frac = ts.partition(".")
    ms = int((frac + "000")[:3]) if frac else 0
    parts = main.split(":")
    if len(parts) == 2:
        parts = ["0"] + parts
    h, m, s = (int(p) for p in parts)
    return h * 3600000 + m * 60000 + s * 1000 + ms


def parse_vtt_timeline(content):
    """
    Return a flat list of (word, start_ms, end_ms) events plus a flag whether
    the captions are word-timestamped (auto) or not (manual).
    Words are ordered by their appearance in the timeline.

    YouTube auto-captions interleave two cue styles: the real word-timestamped
    line (every<00:00:00.320><c> day</c>...) and a plain-text "echo" of the
    same segment with no inline timestamps. When ANY cue carries inline
    timestamps we use only those cues (dropping echoes); otherwise we treat the
    track as manual and spread each cue's duration evenly over its words.
    """
    cue_pattern = re.compile(
        r"(\d{1,2}:\d{2}:\d{2}[.,]\d{3}|\d{1,2}:\d{2}:\d{2}[.,]\d{3})\s*-->"
        r"\s*(\d{1,2}:\d{2}:\d{2}[.,]\d{3}|\d{1,2}:\d{2}[.,]\d{3})"
    )
    inline_ts = re.compile(r"<(\d{1,2}:\d{2}:\d{2}[.,]\d{3})>")
    tag = re.compile(r"</?c[^>]*>|<[^>]*>")

    raw_cues = []  # (start_ms, end_ms, had_inline, pieces)
    lines = content.splitlines()
    i = 0
    any_inline = False
    while i < len(lines):
        line = lines[i]
        m = cue_pattern.search(line)
        if m:
            start_ms = _ts_parse(m.group(1).replace(",", "."))
            end_ms = _ts_parse(m.group(2).replace(",", "."))
            text_lines = []
            i += 1
            while i < len(lines) and lines[i] != "":
                text_lines.append(lines[i])
                i += 1
            raw = " ".join(text_lines)
            raw = raw.replace("&nbsp;", " ").replace("&amp;", "&")
            pieces = re.split(r"(<\d{1,2}:\d{2}:\d{2}[.,]\d{3}>)", raw)
            had_inline = any(inline_ts.match(p) for p in pieces)
            any_inline = any_inline or had_inline
            raw_cues.append((start_ms, end_ms, had_inline, pieces))
        else:
            i += 1

    events = []
    for start_ms, end_ms, had_inline, pieces in raw_cues:
        if any_inline and not had_inline:
            # Echo/duplicate plain-text line of an auto track: ignore.
            continue
        if not had_inline:
            # Manual captions: spread the cue duration evenly over words.
            text = tag.sub("", " ".join(p for p in pieces))
            text = text.replace("&nbsp;", " ").strip()
            words = text.split()
            if words:
                step = (end_ms - start_ms) / len(words)
                for idx, w in enumerate(words):
                    st = int(start_ms + idx * step)
                    en = int(start_ms + (idx + 1) * step)
                    events.append((w, st, en))
            continue
        # Auto track: YouTube pads each real word with an inline timestamp
        # marking its end (`every<00:00:00.320>`). Groups of plain words with
        # no adjacent timestamp are echoes of the previous segment and are
        # dropped so the timeline stays contiguous and duplicate-free.
        groups = []  # list of (words_list, ts_before_ms, ts_after_ms)
        prev_ts = None
        pending_text = []
        for piece in pieces:
            tm = inline_ts.match(piece)
            if tm:
                ts = _ts_parse(tm.group(1).replace(",", "."))
                if pending_text:
                    # Words seen so far end at this timestamp.
                    groups.append((pending_text, prev_ts, ts))
                    pending_text = []
                prev_ts = ts
                continue
            seg = tag.sub("", piece)
            seg = seg.replace("&nbsp;", " ").strip()
            if seg:
                pending_text = pending_text + seg.split()
        if pending_text:
            groups.append((pending_text, prev_ts, None))

        for words, ts_before, ts_after in groups:
            if not words:
                continue
            if ts_before is None and ts_after is None:
                # Echo group: no timestamp on either side.
                continue
            group_start = ts_before if ts_before is not None else (events[-1][2]
                                                                   if events else start_ms)
            group_end = ts_after if ts_after is not None else end_ms
            if group_end < group_start:
                group_end = group_start
            if len(words) == 1:
                events.append((words[0], group_start, group_end))
            else:
                # Distribute within the group (rare; most groups are one word).
                step = (group_end - group_start) / len(words)
                for idx, w in enumerate(words):
                    st = int(group_start + idx * step)
                    en = int(group_start + (idx + 1) * step)
                    events.append((w, st, en))

    # Normalize every event word exactly like phrase words so caption tokens
    # like "150,000" match phrase tokens ["150", "000"]. Each sub-token keeps
    # the time span of its source word.
    normalized_events = []
    for w, st, en in events:
        toks = normalize_words(w)
        if not toks:
            continue
        span = (en - st) / len(toks)
        for i, t in enumerate(toks):
            normalized_events.append(
                (t, int(st + i * span), int(st + (i + 1) * span)))
    return normalized_events, any_inline


def find_phrase_events(events, phrase_words):
    """
    Return a list of (start_ms, end_ms) slices where phrase_words occur
    consecutively in the timeline (allowing small inter-word gaps).
    Hits whose duration is physically implausible for a k-word phrase are
    dropped: YouTube ASR sometimes compresses rapid repeats into overlapping
    word stamps that would otherwise produce unusably tiny slices.
    """
    hits = []
    n = len(events)
    k = len(phrase_words)
    if k == 0 or n == 0:
        return hits
    min_dur = k * 100  # ~100ms per word floor; e.g. 3 words < 300ms is junk
    for i in range(n - k + 1):
        ok = True
        for j in range(k):
            ev = events[i + j]
            w = ev[0].lower()
            target = phrase_words[j]
            if w != target:
                ok = False
                break
        if not ok:
            continue
        # Check inter-word gaps stay within a spoken segment.
        for j in range(k - 1):
            gap = events[i + j + 1][1] - events[i + j][2]
            if gap > MAX_WORD_GAP_MS:
                ok = False
                break
        if not ok:
            continue
        start_ms = events[i][1]
        end_ms = events[i + k - 1][2]
        if end_ms - start_ms >= min_dur:
            hits.append((start_ms, end_ms))
    return hits


# ---------------------------------------------------------------------------
# YouTube search + caption download
# ---------------------------------------------------------------------------
def search_and_fetch_subtitles(phrase, results=DEFAULT_RESULTS):
    """
    Search YouTube for `phrase`, download English captions for the top results,
    and return (id_to_meta, list_of_vtt_paths, tmp_dir).
    (Titles and captions are fetched separately because combining yt-dlp's
    --print with subtitle downloads silently drops the subtitle files.)
    """
    query = f"ytsearch{results}:" + json.dumps(phrase)[1:-1]
    tmp = tempfile.mkdtemp(prefix="ytph_")

    meta = {}
    try:
        meta_proc = subprocess.run(
            [sys.executable, "-m", "yt_dlp", query, "--flat-playlist",
             "--no-warnings", "--print", "%(id)s\t%(title)s"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            timeout=120)
        for line in meta_proc.stdout.splitlines():
            id_, _, title = line.partition("\t")
            if id_ and id_.strip():
                meta[id_.strip()] = title.strip()
    except Exception:
        pass

    cmd = [
        sys.executable, "-m", "yt_dlp",
        query,
        "--skip-download",
        "--write-auto-subs", "--write-subs",
        "--sub-langs", "en,en-orig,en.",
        "--no-playlist",
        "--retries", "3",
        "--sleep-requests", "2",
        "-o", os.path.join(tmp, "%(id)s.%(ext)s"),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True,
                          timeout=300)
    vtts = glob.glob(os.path.join(tmp, "*.vtt"))
    return meta, vtts, tmp


def pick_best_vtt(vtt_files):
    """
    Choose the captions file most likely to carry word timestamps.
    Prefer files matching 'en[.-.]*' patterns without region suffixes, and
    prefer auto tracks ('en-orig', 'en.vtt'). Fall back to any .vtt.
    """
    def score(path):
        base = os.path.basename(path)
        s = 0
        if "orig" in base:
            s += 40
        if re.search(r"\.en\.vtt$", base) or ".en." in base:
            s += 20
        if re.search(r"en-\w+", base):
            s -= 10
        return s
    if not vtt_files:
        return None
    return max(vtt_files, key=score)


# ---------------------------------------------------------------------------
# Phrase database
# ---------------------------------------------------------------------------
def load_db(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_db(db, path):
    new_path = path + ".new"
    with open(new_path, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=1, ensure_ascii=False)
    print(f"[+] Wrote {new_path}")
    return new_path


def build_phrase_candidates(phrase, results=DEFAULT_RESULTS, max_candidates=DEFAULT_MAX_CANDIDATES):
    """Search YouTube for an exact phrase; return list of candidate slices."""
    phrase_words = normalize_words(phrase)
    key = words_to_key(phrase_words)
    meta, vtts, tmp = search_and_fetch_subtitles(phrase, results=results)
    candidates = []
    seen = set()
    for vtt in vtts:
        video_id = os.path.basename(vtt).split(".")[0]
        with open(vtt, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        events, saw_inline = parse_vtt_timeline(content)
        hits = find_phrase_events(events, phrase_words)
        if not hits:
            continue
        # Prefer the occurrence closest to a natural speaking rate
        # (~275ms per word), not the tightest; compressed ASR repeats are
        # already filtered out by find_phrase_events, and this avoids slicing
        # unnaturally clipped deliveries.
        best = min(hits, key=lambda h: abs((h[1] - h[0]) - len(phrase_words) * 275))
        best_start, best_end = best
        if (video_id, best_start, best_end) in seen:
            continue
        seen.add((video_id, best_start, best_end))
        candidates.append({
            "video_id": video_id,
            "title": meta.get(video_id, ""),
            "start_ms": best_start,
            "end_ms": best_end,
            "duration_ms": best_end - best_start,
            "track": "auto" if saw_inline else "manual",
        })
        if len(candidates) >= max_candidates:
            break
    candidates.sort(key=lambda c: (c["duration_ms"], c["start_ms"]))
    try:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    except Exception:
        pass
    return key, candidates


def candidates_from_vtt_file(vtt_path, phrase_words, meta):
    """Extract (events, saw_inline) for a downloaded caption file, returning
    the best time slice where `phrase_words` occur, or None."""
    with open(vtt_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    events, saw_inline = parse_vtt_timeline(content)
    hits = find_phrase_events(events, phrase_words)
    if not hits:
        return None
    best = min(hits, key=lambda h: abs((h[1] - h[0]) - len(phrase_words) * 275))
    best_start, best_end = best
    return (best_start, best_end, len(events), saw_inline)


def harvest_from_videos(video_ids, phrase_keys, max_candidates=DEFAULT_MAX_CANDIDATES):
    """
    Download captions from a set of known video IDs and extract candidate
    slices for every phrase listed. Returns (phrase_key -> [candidates]).
    """
    found = {}
    for video_id in video_ids:
        tmp = tempfile.mkdtemp(prefix="ythr_")
        try:
            cmd = [
                sys.executable, "-m", "yt_dlp",
                f"https://www.youtube.com/watch?v={video_id}",
                "--skip-download", "--write-auto-subs", "--write-subs",
                "--sub-langs", "en,en-orig,en.", "--no-playlist",
                "--retries", "3", "--sleep-requests", "2",
                "-o", os.path.join(tmp, "%(id)s.%(ext)s"),
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=300)
            vtts = glob.glob(os.path.join(tmp, "*.vtt"))
            if not vtts:
                print(f"[!] No captions for {video_id}")
                continue
            vtt = pick_best_vtt(vtts)
            print(f"[*] {video_id}: {len(vtts)} caption file(s) -> {os.path.basename(vtt)}")
            for key, phrase_words in phrase_keys.items():
                res = candidates_from_vtt_file(vtt, phrase_words, {})
                if not res:
                    continue
                best_start, best_end, _, saw_inline = res
                cand = {
                    "video_id": video_id,
                    "title": video_id,
                    "start_ms": best_start,
                    "end_ms": best_end,
                    "duration_ms": best_end - best_start,
                    "track": "auto" if saw_inline else "manual",
                }
                found.setdefault(key, []).append(cand)
        finally:
            try:
                import shutil
                shutil.rmtree(tmp, ignore_errors=True)
            except Exception:
                pass
    return found


def shingle_text(text, min_words, max_words):
    tokens = normalize_words(text)
    out = set()
    n = len(tokens)
    for start in range(n):
        for length in range(min_words, min(max_words, n - start) + 1):
            out.add(words_to_key(tokens[start:start + length]))
    return sorted(out)


def main():
    ap = argparse.ArgumentParser(description="Build phrase_db.json from YouTube captions")
    ap.add_argument("phrases", nargs="*", help="Exact phrases to search for")
    ap.add_argument("--sentence", help="A sentence; every n-gram (min..max words) is added as a phrase")
    ap.add_argument("--min-words", type=int, default=3)
    ap.add_argument("--max-words", type=int, default=6)
    ap.add_argument("--results", type=int, default=DEFAULT_RESULTS)
    ap.add_argument("--max-candidates", type=int, default=DEFAULT_MAX_CANDIDATES)
    ap.add_argument("--video", action="append", default=[],
                    help="YouTube video ID to harvest captions from (repeatable)")
    ap.add_argument("--db", default=os.path.join(REPO, "phrase_db.json"))
    ap.add_argument("--commit", action="store_true", help="Overwrite phrase_db.json")
    args = ap.parse_args()

    phrases = list(args.phrases)
    if args.sentence:
        phrases.extend(shingle_text(args.sentence, args.min_words, args.max_words))
    phrases = [re.sub(r"\s+", " ", p).strip() for p in phrases if p.strip()]
    if not phrases:
        ap.print_help()
        sys.exit(1)

    db = load_db(args.db)
    before = sum(len(v) for v in db.values())

    # De-duplicate while preserving a stable order (longest phrases first).
    unique = sorted(set(phrases), key=lambda p: (-len(normalize_words(p)), p))

    key_to_phrase = {words_to_key(normalize_words(p)): p for p in unique}

    if args.video:
        wanted = {k: normalize_words(p) for k, p in key_to_phrase.items()
                  if k not in db or not db.get(k)}
        if wanted:
            print(f"[*] Harvesting {len(wanted)} phrase(s) from {len(args.video)} seeded video(s)...")
            harvested = harvest_from_videos(args.video, wanted, args.max_candidates)
            for key, cands in harvested.items():
                db.setdefault(key, []).extend(cands[:args.max_candidates])
                print(f"[+] {len(cands)} candidate(s) for {key_to_phrase[key]!r} "
                      f"(from {','.join(c['video_id'] for c in cands[:3])})")

    for phrase in unique:
        key = words_to_key(normalize_words(phrase))
        if key in db and db[key]:
            print(f"[skip] already in DB: {key!r}")
            continue
        print(f"[*] Searching YouTube for: {phrase!r} ...")
        try:
            key2, candidates = build_phrase_candidates(phrase, args.results, args.max_candidates)
        except subprocess.TimeoutExpired:
            print("[!] Search timed out; skipped.")
            continue
        except Exception as e:
            print(f"[!] Search failed ({e}); skipped.")
            continue
        if candidates:
            db.setdefault(key2, []).extend(candidates)
            print(f"[+] {len(candidates)} candidate(s) for {key2!r}:")
            for c in candidates[:3]:
                print(f"    - {c['video_id']}  {c['duration_ms']}ms  "
                      f"[{c['start_ms']}..{c['end_ms']}]  ({c['track']})  {c['title'][:50]}")
        else:
            print(f"[-] No exact occurrence found for: {key!r}")

    after = sum(len(v) for v in db.values())
    print(f"[*] {len(db)} phrases, {after} candidates total "
          f"(+{after - before} new).")

    new_path = save_db(db, args.db)
    if args.commit:
        os.replace(new_path, args.db)
        print("[*] Committed to phrase_db.json")
    else:
        print("[*] Dry run — nothing overwritten. Re-run with --commit.")


if __name__ == "__main__":
    main()