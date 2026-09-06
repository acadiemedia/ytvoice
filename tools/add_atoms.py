#!/usr/bin/env python3
"""
Add a library of sub-word "atoms" (phonograms, digraphs/trigraphs, prefixes,
suffixes, and combining forms) to voice_sprites.bin so the player's
segment_word() recombination can assemble (almost) any English word from a
small, curated sound inventory.

Each atom key is a *grapheme* (ASCII spelling) that can appear as a substring
of real English words.  The audio is synthesized as the atom's *pronunciation*
by feeding raw phoneme symbols straight to Piper's phoneme path (espeak's
isolated-string fallback would otherwise spell the grapheme out letter by
letter), then resampled to the bin's 16kHz-mono IMA ADPCM container.

New keys that already exist in the index are skipped (never overwritten).

Usage:
    python tools/add_atoms.py [--model PATH] [--commit]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import io
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "src"))

import ffmpeg_util  # noqa: E402

# ---------------------------------------------------------------------------
# Grapheme -> pronunciation (raw espeak phoneme symbols; see the model's
# phoneme_id_map for the accepted symbol set).
# ---------------------------------------------------------------------------
PH = {
    # ---- Vowel sounds (isolated) -----------------------------------------
    "a": ["æ"],
    "e": ["ɛ"],
    "i": ["ɪ"],
    "o": ["ɒ"],
    "u": ["ʌ"],
    "ae": ["iː"],
    "ah": ["ɑː"],
    "oo": ["uː"],
    "er": ["ɜː"],
    "ow": ["aʊ"],
    "oy": ["ɔɪ"],
    "ai": ["eɪ"],
    "ay": ["eɪ"],
    "ea": ["iː"],
    "ee": ["iː"],
    "ei": ["eɪ"],
    "oa": ["oʊ"],
    "oe": ["oʊ"],
    "oi": ["ɔɪ"],
    "ou": ["aʊ"],
    "au": ["ɔː"],
    "aw": ["ɔː"],
    "ew": ["uː"],
    "ey": ["iː"],
    "ie": ["iː"],
    "ue": ["uː"],
    "ui": ["uː"],
    "eigh": ["eɪ"],
    "igh": ["aɪ"],
    "ough": ["ɔː"],
    "augh": ["ɔː"],

    # ---- r-colored vowels -------------------------------------------------
    "ar": ["ˈɑː"],
    "or": ["ˈɔː"],
    "ir": ["ˈɜː"],
    "ur": ["ˈɜː"],
    "ear": ["ˈɪə"],
    "air": ["ˈɛə"],
    "oar": ["ˈɔː"],
    "oor": ["ˈɔː"],
    "our": ["ˈaʊə"],
    "eir": ["ˈɛə"],
    "w": ["ˈw"],  # placeholder never used; letters handled separately

    # ---- consonant digraphs / trigraphs -----------------------------------
    "sh": ["ʃ"],
    "ch": ["tʃ"],
    "th": ["θ"],
    "wh": ["w"],
    "ph": ["f"],
    "ng": ["ŋ"],
    "ck": ["k"],
    "qu": ["kw"],
    "tch": ["tʃ"],
    "dge": ["dʒ"],
    "wr": ["ɹ"],
    "kn": ["n"],
    "gn": ["n"],
    "mb": ["m"],
    "mn": ["m"],
    "ps": ["s"],
    "pt": ["t"],
    "rh": ["ɹ"],
    "gh": ["ɡ"],
    "zh": ["ʒ"],
    "tt": ["t"],
    "ss": ["s"],
    "ff": ["f"],
    "ll": ["l"],
    "pp": ["p"],
    "rr": ["ɹ"],
    "dd": ["d"],
    "nn": ["n"],
    "bb": ["b"],
    "gg": ["ɡ"],
    "mm": ["m"],
    "vv": ["v"],
    "kk": ["k"],
    "sc": ["sk"],

    # ---- inflectional & derivational suffixes -----------------------------
    "ing": ["ɪŋ"],
    "ed": ["ɪd"],
    "est": ["ɪst"],
    "erful": ["ɜːfəl"],
    "ful": ["fəl"],
    "less": ["ləs"],
    "ly": ["li"],
    "tion": ["ʃən"],
    "sion": ["ʒən"],
    "ssion": ["ʃən"],
    "cian": ["ʃən"],
    "cious": ["ʃəs"],
    "tious": ["ʃəs"],
    "ness": ["nəs"],
    "ment": ["mənt"],
    "able": ["əbəl"],
    "ible": ["əbəl"],
    "al": ["əl"],
    "ial": ["iəl"],
    "ary": ["ɛɹi"],
    "ory": ["ɔɹi"],
    "ous": ["əs"],
    "ious": ["iəs"],
    "y": ["i"],
    "age": ["ɪdʒ"],
    "dom": ["dəm"],
    "hood": ["hʊd"],
    "ship": ["ʃɪp"],
    "ity": ["ɪti"],
    "ty": ["ti"],
    "ency": ["ənsi"],
    "ancy": ["ənsi"],
    "ence": ["əns"],
    "ance": ["əns"],
    "ent": ["ənt"],
    "ant": ["ənt"],
    "ish": ["ɪʃ"],
    "wise": ["waɪz"],
    "some": ["səm"],
    "ward": ["wəɹd"],
    "logue": ["lɔːɡ"],
    "logy": ["lədʒi"],
    "graphy": ["ɡɹəfi"],
    "phone": ["foʊn"],
    "phobia": ["foʊbiə"],
    "scope": ["skoʊp"],
    "meter": ["mətə"],
    "metric": ["mɛtɹɪk"],
    "gram": ["ɡɹæm"],
    "graph": ["ɡɹæf"],
    "form": ["fɔːɹm"],
    "fold": ["foʊld"],

    # ---- prefixes ----------------------------------------------------------
    "re": ["ɹi"],
    "pre": ["pɹi"],
    "pro": ["pɹoʊ"],
    "post": ["poʊst"],
    "un": ["ʌn"],
    "in": ["ɪn"],
    "im": ["ɪm"],
    "il": ["ɪl"],
    "ir": ["ɪɹ"],
    "dis": ["dɪs"],
    "mis": ["mɪs"],
    "de": ["di"],
    "ab": ["æb"],
    "ad": ["æd"],
    "con": ["kɒn"],
    "com": ["kɒm"],
    "col": ["kɒl"],
    "cor": ["kəɹ"],
    "co": ["koʊ"],
    "sub": ["sʌb"],
    "sup": ["səp"],
    "sus": ["səs"],
    "sur": ["sɜː"],
    "trans": ["tɹæns"],
    "inter": ["ɪntɜː"],
    "intra": ["ɪntɹə"],
    "intro": ["ɪntɹoʊ"],
    "over": ["oʊvɜː"],
    "under": ["ʌndə"],
    "super": ["suːpə"],
    "supra": ["suːpɹə"],
    "hypo": ["haɪpoʊ"],
    "hyper": ["haɪpɜː"],
    "anti": ["ænti"],
    "ante": ["ænti"],
    "semi": ["sɛmi"],
    "mono": ["mɒnoʊ"],
    "bi": ["baɪ"],
    "tri": ["tɹaɪ"],
    "tetra": ["tɛtɹə"],
    "penta": ["pɛntə"],
    "hexa": ["hɛksə"],
    "hepta": ["hɛptə"],
    "octa": ["ɒktə"],
    "nona": ["nɒnə"],
    "deca": ["dɛkə"],
    "centi": ["sɛntɪ"],
    "milli": ["mɪli"],
    "kilo": ["kɪloʊ"],
    "mega": ["mɛɡə"],
    "giga": ["ɡɪɡə"],
    "micro": ["maɪkɹoʊ"],
    "macro": ["mækɹoʊ"],
    "multi": ["mʌlti"],
    "poly": ["pɒli"],
    "self": ["sɛlf"],
    "extra": ["ɛkstɹə"],
    "exo": ["ɛksoʊ"],
    "omni": ["ɒmni"],
    "fore": ["fɔː"],
    "contra": ["kɒntɹə"],
    "counter": ["kaʊntə"],
    "para": ["pæɹə"],
    "peri": ["pɛɹi"],
    "circum": ["sɜːkəm"],
    "mal": ["mæl"],
    "retro": ["ɹɛtɹoʊ"],
    "ultra": ["ʌltɹə"],
    "vice": ["vaɪs"],
    "bene": ["bɛni"],
    "epi": ["ɛpi"],
    "mid": ["mɪd"],
    "out": ["aʊt"],
    "up": ["ʌp"],
    "down": ["daʊn"],
    "non": ["nɒn"],
    "pref": ["pɹiː"],
    "suffix": ["sʌfɪks"],

    # ---- combining forms / common roots ------------------------------------
    "bio": ["baɪoʊ"],
    "geo": ["dʒiːoʊ"],
    "auto": ["ɔːtoʊ"],
    "tele": ["tɛli"],
    "hydro": ["haɪdɹə"],
    "thermo": ["θɜːmoʊ"],
    "photo": ["foʊtoʊ"],
    "electro": ["ilɛktɹoʊ"],
    "astro": ["æstɹoʊ"],
    "audio": ["ɔːdiːoʊ"],
    "anthropo": ["ænθɹəpoʊ"],
    "crypto": ["kɹɪptoʊ"],
    "demo": ["dɛmoʊ"],
    "eco": ["iːkoʊ"],
    "endo": ["ɛndoʊ"],
    "exo": ["ɛksoʊ"],
    "hetero": ["hɛtəɹoʊ"],
    "homo": ["hoʊmoʊ"],
    "iso": ["aɪsoʊ"],
    "magni": ["mæɡni"],
    "maxi": ["mæksi"],
    "mini": ["mɪni"],
    "pseudo": ["suːdoʊ"],
    "proto": ["pɹoʊtoʊ"],
    "psycho": ["saɪkoʊ"],
    "retro": ["ɹɛtɹoʊ"],
    "tech": ["tɛk"],
    "theo": ["θiːoʊ"],
    "techno": ["tɛknoʊ"],
    "tri": ["tɹaɪ"],
    "uni": ["juːni"],

    # ---- common syllables/units (for smoother recombination) ---------------
    "should": ["ʃəd"],
    "would": ["wʊd"],
    "could": ["kʊd"],
    "about": ["əbaʊt"],
    "above": ["əbʌv"],
    "again": ["əɡɛn"],
    "against": ["əɡɛnst"],
    "around": ["əɹaʊnd"],
    "behind": ["bɪhaɪnd"],
    "below": ["bɪloʊ"],
    "before": ["bɪfɔː"],
    "after": ["æftə"],
    "during": ["dʒʊəɹɪŋ"],
    "within": ["wɪðɪn"],
    "without": ["wɪðaʊt"],
    "along": ["əlɒŋ"],
    "among": ["əmʌŋ"],
    "between": ["bɪtwiːn"],
    "through": ["θɹuː"],
    "throughout": ["θɹuːaʊt"],
    "the": ["ðə"],
    "and": ["ænd"],
    "you": ["juː"],
    "have": ["hæv"],
    "has": ["hæz"],
    "had": ["hæd"],
    "with": ["wɪð"],
    "from": ["fɹɒm"],
    "which": ["wɪtʃ"],
    "their": ["ðɛə"],
    "there": ["ðɛə"],
    "they": ["ðeɪ"],
    "them": ["ðɛm"],
    "these": ["ðiːz"],
    "this": ["ðɪs"],
    "those": ["ðoʊz"],
    "that": ["ðæt"],
    "then": ["ðɛn"],
    "than": ["ðæn"],
    "when": ["wɛn"],
    "where": ["wɛə"],
    "what": ["wɒt"],
    "why": ["waɪ"],
    "whom": ["huːm"],
    "who": ["huː"],
    "were": ["wɜː"],
    "are": ["ɑː"],
    "was": ["wɒz"],
    "not": ["nɒt"],
    "but": ["bʌt"],
    "for": ["fɔː"],
    "of": ["ɒv"],
    "off": ["ɔːf"],
    "on": ["ɒn"],
    "in": ["ɪn"],
    "into": ["ɪntuː"],
    "it": ["ɪt"],
    "its": ["ɪts"],
    "is": ["ɪz"],
    "be": ["bi"],
    "been": ["bɪn"],
    "am": ["æm"],
    "can": ["kæn"],
    "may": ["meɪ"],
    "shall": ["ʃæl"],
    "will": ["wɪl"],
    "would": ["wʊd"],
    "should": ["ʃʊd"],
    "only": ["oʊnli"],
    "own": ["oʊn"],
    "most": ["moʊst"],
    "more": ["mɔː"],
    "much": ["mʌtʃ"],
    "many": ["mɛni"],
    "such": ["sʌtʃ"],
    "other": ["ʌðə"],
    "another": ["ənʌðə"],
    "first": ["fɜːst"],
    "last": ["læst"],
    "great": ["ɡɹeɪt"],
    "good": ["ɡʊd"],
    "well": ["wɛl"],
    "just": ["dʒʌst"],
    "very": ["vɛɹi"],
    "also": ["ɔːlsoʊ"],
    "too": ["tuː"],
    "some": ["sʌm"],
    "any": ["ɛni"],
    "every": ["ɛvɹi"],
    "one": ["wʌn"],
    "two": ["tuː"],
    "three": ["θɹiː"],
    "four": ["fɔː"],
    "five": ["faɪv"],
    "six": ["sɪks"],
    "seven": ["sɛvən"],
    "eight": ["eɪt"],
    "nine": ["naɪn"],
    "ten": ["tɛn"],
    "into": ["ɪntuː"],
    "upon": ["əpɒn"],
    "here": ["hɪə"],
    "there": ["ðɛə"],
    "example": ["ɪɡzɑːmpəl"],
    "because": ["bɪkɒz"],
    "people": ["piːpəl"],
    "water": ["wɔːtə"],
    "through": ["θɹuː"],
    "though": ["ðoʊ"],
    "thought": ["θɔːt"],
    "about": ["əbaʊt"],
    "always": ["ɔːlweɪz"],
    "being": ["biːɪŋ"],
    "both": ["boʊθ"],
    "call": ["kɔːl"],
    "come": ["kʌm"],
    "day": ["deɪ"],
    "find": ["faɪnd"],
    "give": ["ɡɪv"],
    "go": ["ɡoʊ"],
    "hear": ["hɪə"],
    "keep": ["kiːp"],
    "know": ["noʊ"],
    "make": ["meɪk"],
    "say": ["seɪ"],
    "see": ["siː"],
    "take": ["teɪk"],
    "tell": ["tɛl"],
    "think": ["θɪŋk"],
    "use": ["juːz"],
    "want": ["wɒnt"],
    "work": ["wɜːk"],
    "year": ["jɪə"],
    "way": ["weɪ"],
    "world": ["wɜːld"],
    "thing": ["θɪŋ"],
    "hand": ["hænd"],
    "face": ["feɪs"],
    "life": ["laɪf"],
    "time": ["taɪm"],
    "man": ["mæn"],
    "woman": ["wʊmən"],
    "men": ["mɛn"],
    "child": ["tʃaɪld"],
    "children": ["tʃɪldɹən"],
    "house": ["haʊs"],
    "home": ["hoʊm"],
    "mother": ["mʌðə"],
    "father": ["fɑːðə"],
    "brother": ["bɹʌðə"],
    "sister": ["sɪstə"],
    "friend": ["fɹɛnd"],
    "air": ["ɛə"],
    "earth": ["ɜːθ"],
    "fire": ["faɪə"],
    "water": ["wɔːtə"],
    "sun": ["sʌn"],
    "moon": ["muːn"],
    "star": ["stɑː"],
    "night": ["naɪt"],
    "day": ["deɪ"],
    "light": ["laɪt"],
    "right": ["ɹaɪt"],
    "left": ["lɛft"],
    "top": ["tɒp"],
    "bottom": ["bɒtəm"],
    "high": ["haɪ"],
    "low": ["loʊ"],
    "big": ["bɪɡ"],
    "small": ["smɔːl"],
    "long": ["lɒŋ"],
    "short": ["ʃɔːt"],
    "old": ["oʊld"],
    "new": ["njuː"],
    "young": ["jʌŋ"],
    "hot": ["hɒt"],
    "cold": ["koʊld"],
    "warm": ["wɔːm"],
    "cool": ["kuːl"],
    "dry": ["dɹaɪ"],
    "wet": ["wɛt"],
    "open": ["oʊpən"],
    "close": ["kloʊz"],
    "hard": ["hɑːd"],
    "soft": ["sɒft"],
    "fast": ["fæst"],
    "slow": ["sloʊ"],
    "strong": ["stɹɒŋ"],
    "weak": ["wiːk"],
    "full": ["fʊl"],
    "empty": ["ɛmpti"],
    "true": ["tɹuː"],
    "false": ["fɔːls"],
    "black": ["blæk"],
    "white": ["waɪt"],
    "red": ["ɹɛd"],
    "green": ["ɡɹiːn"],
    "blue": ["bluː"],
    "yellow": ["jɛloʊ"],
    "brown": ["bɹaʊn"],
    "purple": ["pɜːpəl"],
    "pink": ["pɪŋk"],
    "orange": ["ɒɹɪndʒ"],
    "gray": ["ɡɹeɪ"],
    "grey": ["ɡɹeɪ"],
    "before": ["bɪfɔː"],
    "peace": ["piːs"],
    "war": ["wɔː"],
    "love": ["lʌv"],
    "hate": ["heɪt"],
    "good": ["ɡʊd"],
    "bad": ["bæd"],
    "day": ["deɪ"],
    "week": ["wiːk"],
    "month": ["mʌnθ"],
    "year": ["jɪə"],
    "today": ["tədeɪ"],
    "tomorrow": ["təmɒɹoʊ"],
    "yesterday": ["jɛstəɹdeɪ"],
    "breakfast": ["bɹɛkfəst"],
    "lunch": ["lʌntʃ"],
    "dinner": ["dɪnə"],
    "water": ["wɔːtə"],
    "food": ["fuːd"],
    "eat": ["iːt"],
    "drink": ["dɹɪŋk"],
    "play": ["pleɪ"],
    "sleep": ["sliːp"],
    "walk": ["wɔːk"],
    "run": ["ɹʌn"],
    "jump": ["dʒʌmp"],
    "sit": ["sɪt"],
    "stand": ["stænd"],
    "school": ["skuːl"],
    "learn": ["lɜːn"],
    "read": ["ɹiːd"],
    "write": ["ɹaɪt"],
    "book": ["bʊk"],
    "paper": ["peɪpə"],
    "pen": ["pɛn"],
    "number": ["nʌmbə"],
    "letter": ["lɛtə"],
    "word": ["wɜːd"],
    "question": ["kwɛstʃən"],
    "answer": ["ænsə"],
    "picture": ["pɪktʃə"],
    "music": ["mjuːzɪk"],
    "song": ["sɒŋ"],
    "dance": ["dæns"],
    "art": ["ɑːt"],
    "science": ["saɪəns"],
    "math": ["mæθ"],
    "problem": ["pɹɒbləm"],
    "family": ["fæmɪli"],
    "person": ["pɜːsən"],
    "people": ["piːpəl"],
    "child": ["tʃaɪld"],
    "baby": ["beɪbi"],
    "boy": ["bɔɪ"],
    "girl": ["ɡɜːl"],
    "man": ["mæn"],
    "woman": ["wʊmən"],
    "city": ["sɪti"],
    "town": ["taʊn"],
    "country": ["kʌntɹi"],
    "state": ["steɪt"],
    "world": ["wɜːld"],
    "space": ["speɪs"],
    "earth": ["ɜːθ"],
    "sun": ["sʌn"],
    "moon": ["muːn"],
    "language": ["læŋɡwɪdʒ"],
    "english": ["ɪŋɡlɪʃ"],
    "system": ["sɪstəm"],
    "machine": ["məʃiːn"],
    "computer": ["kəmpjuːtə"],
    "phone": ["foʊn"],
    "music": ["mjuːzɪk"],
    "team": ["tiːm"],
    "game": ["ɡeɪm"],
    "group": ["ɡɹuːp"],
    "part": ["pɑːt"],
    "place": ["pleɪs"],
    "point": ["pɔɪnt"],
    "story": ["stɔːɹi"],
    "line": ["laɪn"],
    "head": ["hɛd"],
    "heart": ["hɑːt"],
    "body": ["bɒdi"],
    "eye": ["aɪ"],
    "ear": ["ɪə"],
    "nose": ["noʊz"],
    "mouth": ["maʊθ"],
    "hair": ["hɛə"],
    "hand": ["hænd"],
    "foot": ["fʊt"],
    "leg": ["lɛɡ"],
    "arm": ["ɑːm"],
    "face": ["feɪs"],
    "skin": ["skɪn"],
    "brain": ["bɹeɪn"],
    "blood": ["blʌd"],
    "bone": ["boʊn"],
    "back": ["bæk"],
    "front": ["fɹʌnt"],
    "side": ["saɪd"],
    "top": ["tɒp"],
    "bottom": ["bɒtəm"],
    "start": ["stɑːt"],
    "stop": ["stɒp"],
    "turn": ["tɜːn"],
    "move": ["muːv"],
    "hold": ["hoʊld"],
    "carry": ["kæɹi"],
    "begin": ["bɪɡɪn"],
    "end": ["ɛnd"],
    "continue": ["kəntɪnjuː"],
    "change": ["tʃeɪndʒ"],
    "get": ["ɡɛt"],
    "put": ["pʊt"],
    "help": ["hɛlp"],
    "show": ["ʃoʊ"],
    "look": ["lʊk"],
    "listen": ["lɪsən"],
    "speak": ["spiːk"],
    "talk": ["tɔːk"],
    "hear": ["hɪə"],
    "smell": ["smɛl"],
    "taste": ["teɪst"],
    "touch": ["tʌtʃ"],
    "feel": ["fiːl"],
    "know": ["noʊ"],
    "think": ["θɪŋk"],
    "believe": ["bɪliːv"],
    "understand": ["ʌndəstænd"],
    "remember": ["ɹɪmɛmbə"],
    "forget": ["fəɡɛt"],
    "try": ["tɹaɪ"],
    "work": ["wɜːk"],
    "live": ["lɪv"],
    "die": ["daɪ"],
    "born": ["bɔːn"],
    "free": ["fɹiː"],
    "happy": ["hæpi"],
    "sad": ["sæd"],
    "angry": ["æŋɡɹi"],
    "scared": ["skɛəd"],
    "sleepy": ["sliːpi"],
    "tired": ["taɪəd"],
}


def load_symbols(config_path):
    """Return the set of phoneme symbols the model's id map accepts."""
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return set(cfg["phoneme_id_map"].keys())


def parse_transcription(symbols, s):
    """Split a phoneme transcription string into the model's symbol tokens."""
    syms = sorted(symbols, key=len, reverse=True)
    out = []
    i = 0
    while i < len(s):
        for sym in syms:
            if s.startswith(sym, i):
                out.append(sym)
                i += len(sym)
                break
        else:
            raise ValueError(f"cannot parse {s!r} at position {i}: {s[i:]!r}")
    return out


def to_adpcm_wav(ffmpeg, wave_bytes):
    """Resample a 22050Hz mono PCM WAV to 16kHz mono IMA ADPCM WAV bytes."""
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in.wav")
        dst = os.path.join(tmp, "out.wav")
        with open(src, "wb") as f:
            f.write(wave_bytes)
        cmd = [ffmpeg, "-y", "-i", src, "-ar", "16000", "-ac", "1",
               "-c:a", "adpcm_ima_wav", dst]
        subprocess.run(cmd, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        with open(dst, "rb") as f:
            return f.read()


def synth_phonemes(voice, tokens):
    """Synthesize raw phoneme tokens in-process; return PCM WAV bytes."""
    ids = voice.phonemes_to_ids(tokens)
    audio = voice.phoneme_ids_to_audio(ids)
    if isinstance(audio, tuple):
        audio = audio[0]
    if audio.dtype != np.float32:
        audio = audio.astype(np.float32)
    pcm = (audio * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(voice.config.sample_rate)
        f.writeframes(pcm.tobytes())
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser(description="Add sub-word atoms to voice_sprites.bin")
    ap.add_argument("--model", default=r"X:\piper\voices\en_US-amy-medium.onnx")
    ap.add_argument("--commit", action="store_true",
                    help="Write changes into the repo's bin/index (creates .bak)")
    args = ap.parse_args()

    config_path = args.model + ".json"
    if not os.path.exists(args.model) or not os.path.exists(config_path):
        print(f"[Error] Model or config missing: {args.model}")
        sys.exit(1)

    bin_path = os.path.join(REPO, "voice_sprites.bin")
    index_path = os.path.join(REPO, "voice_sprites.bin.index.json")
    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)

    # Atoms to add: only keys not already present, and only valid ones.
    skip = set()
    for k in PH:
        if not k or not k.islower() or not k.isascii() or k in index:
            skip.add(k)
    print(f"[*] {len(PH) - len(skip)} atom keys to evaluate "
          f"({len(PH)} in table, {len(skip)} skipped)")

    if not (PH.keys() - skip):
        print("[*] Nothing to add.")
        return

    from piper.voice import PiperVoice
    voice = PiperVoice.load(args.model)
    symbols = load_symbols(config_path)
    ffmpeg = ffmpeg_util.get_ffmpeg_exe()

    # Parse transcription strings into phoneme token lists; filter invalid.
    atoms = {}
    parse_failed = []
    for k, raw in sorted(PH.items()):
        if k in skip:
            continue
        s = raw[0] if isinstance(raw, list) else raw
        try:
            toks = parse_transcription(symbols, s)
        except ValueError as ex:
            parse_failed.append((k, str(ex)))
            continue
        atoms[k] = toks

    if parse_failed:
        print(f"[!] {len(parse_failed)} atoms have invalid phoneme symbols:")
        for k, reason in parse_failed[:30]:
            print(f"    {k!r}: {reason}")
        if len(parse_failed) > 30:
            print(f"    ... and {len(parse_failed)-30} more")

    print(f"[*] {len(atoms)} atoms ready to synthesize")

    if not atoms:
        print("[*] Nothing to add.")
        return

    data = bytearray()
    with open(bin_path, "rb") as f:
        data += f.read()

    failed_keys = set()
    data2 = bytearray(data)
    offsets2 = {}
    for k, toks in sorted(atoms.items()):
        if k in failed_keys:
            continue
        try:
            wav = synth_phonemes(voice, toks)
            blob = to_adpcm_wav(ffmpeg, wav)
        except Exception as ex:
            failed_keys.add(k)
            continue
        if not blob or len(blob) < 128:
            continue
        offsets2[k] = [len(data2), len(blob)]
        data2 += blob
    final_index = dict(index)
    final_index.update(offsets2)
    final_blob = bytes(data2)

    skipped = [k for k in PH if k in index]
    print(f"[+] Added {len(offsets2)} atoms, total index entries "
          f"{len(final_index)}")
    print(f"[+] New bin blob size: {len(final_blob)} bytes "
          f"(added {len(final_blob) - len(data)})")
    if skipped:
        print(f"[*] Already present (skipped): {len(skipped)}")
    if failed_keys:
        print(f"[!] Failed synthesis ({len(failed_keys)}):")
        for k in sorted(failed_keys):
            print(f"    {k!r}")

    new_bin = bin_path + ".new"
    new_index_path = index_path + ".new"
    with open(new_bin, "wb") as f:
        f.write(final_blob)
    with open(new_index_path, "w", encoding="utf-8") as f:
        json.dump(final_index, f)
    print(f"[+] Wrote {new_bin} and {new_index_path}")

    if args.commit:
        for target in (bin_path, index_path):
            if os.path.exists(target):
                os.replace(target, target + ".bak")
        os.replace(new_bin, bin_path)
        os.replace(new_index_path, index_path)
        print("[*] Committed. Backups kept as *.bak")
    else:
        print("[*] Dry run — nothing overwritten. Re-run with --commit.")


if __name__ == "__main__":
    main()