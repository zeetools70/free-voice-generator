"""
Urdu/Hindi/English Voice Generator - Web Version (Streamlit)
Free unlimited TTS using Microsoft's edge-tts engine.
Deploy for free on Streamlit Community Cloud (share.streamlit.io).

DEPLOY KAISE KAREIN (Bilkul Free):
1. github.com per free account banayen (agar nahi hai)
2. Ek naya repository banayen (jaise "voice-generator")
3. Is file ka naam "streamlit_app.py" rakh kar us repo mein upload karein
4. "requirements.txt" bhi upload karein (neeche di gayi hai)
5. share.streamlit.io per jayein, GitHub se sign in karein
6. "New app" per click karein, apni repo select karein, "streamlit_app.py" file select karein
7. "Deploy" per click karein - 2-3 minute mein live ho jayegi, public URL milega

Local per test karne ke liye:
    pip install streamlit edge-tts
    streamlit run streamlit_app.py
"""

import asyncio
import os
import re
import tempfile
import uuid
from datetime import datetime

import edge_tts
import streamlit as st

# ---------------------------------------------------------------------------
# Voices
# ---------------------------------------------------------------------------
VOICES = {
    "Urdu (Male) - Asad — Normal/Narration": "ur-PK-AsadNeural",
    "Urdu (Female) - Uzma — Soft/Calm": "ur-PK-UzmaNeural",
    "Hindi (Male) - Madhur — Narration/News": "hi-IN-MadhurNeural",
    "Hindi (Female) - Swara — Soft/Storytelling": "hi-IN-SwaraNeural",
    "English US (Female) - Aria — Storytelling/Expressive": "en-US-AriaNeural",
    "English US (Female) - Jenny — Soft/Friendly": "en-US-JennyNeural",
    "English US (Female) - Emma — Warm/Clear": "en-US-EmmaNeural",
    "English US (Female) - Ava — Expressive/Caring": "en-US-AvaNeural",
    "English US (Female) - Michelle — Professional/Crisp": "en-US-MichelleNeural",
    "English US (Male) - Guy — Narration/News": "en-US-GuyNeural",
    "English US (Male) - Roger — Deep/Documentary": "en-US-RogerNeural",
    "English US (Male) - Christopher — Deep/Authoritative": "en-US-ChristopherNeural",
    "English US (Male) - Andrew — Warm/Confident Narration": "en-US-AndrewNeural",
    "English US (Male) - Brian — Approachable/Casual": "en-US-BrianNeural",
    "English US (Male) - Eric — Rational/Clear": "en-US-EricNeural",
    "English UK (Female) - Sonia — Calm/Professional": "en-GB-SoniaNeural",
    "English UK (Female) - Libby — Friendly/Positive": "en-GB-LibbyNeural",
    "English UK (Male) - Ryan — Narration/Formal": "en-GB-RyanNeural",
    "English UK (Male) - Thomas — Friendly/General": "en-GB-ThomasNeural",
}

SAMPLE_TEXTS = {
    "ur-PK": "Yeh awaz ka namoona hai. Umeed hai apko pasand ayegi.",
    "hi-IN": "Yeh awaz ka namoona hai. Umeed hai aapko pasand aayegi.",
    "en-US": "This is a sample of this voice. I hope you like how it sounds.",
    "en-GB": "This is a sample of this voice. I hope you like how it sounds.",
}

MAX_CHUNK_CHARS = 1500
PAUSE_PATTERN = re.compile(r"\[pause:\s*(\d+(?:\.\d+)?)\s*\]", re.IGNORECASE)
COMBINED_PATTERN = re.compile(
    r"\[pause:\s*(\d+(?:\.\d+)?)\s*\]|\[voice:\s*([^\]]+?)\s*\]", re.IGNORECASE
)
RATE_MAP = {"Slow": "-20%", "Normal": "+0%", "Fast": "+25%"}


def find_voice_label(name_fragment):
    """[voice:Guy] jaisy marker ko VOICES dictionary ki keys se match karta hai (case-insensitive substring)."""
    fragment = name_fragment.strip().lower()
    for label in VOICES:
        if fragment in label.lower():
            return label
    return None


def parse_script(text, default_voice_label):
    """
    Text ko steps ki list mein todta hai: ("speech", chunk, voice_code) ya ("pause", seconds, voice_code).
    [voice:Name] marker se beech script mein voice badal sakty hain,
    [pause:N] marker se N second ka silence insert hota hai.
    """
    current_label = default_voice_label
    steps = []
    last_end = 0

    def flush_text(segment_text, voice_label):
        voice_code = VOICES[voice_label]
        for chunk in chunk_text(segment_text):
            if chunk.strip():
                steps.append(("speech", chunk, voice_code))

    for m in COMBINED_PATTERN.finditer(text):
        if m.start() > last_end:
            flush_text(text[last_end:m.start()], current_label)

        if m.group(1) is not None:
            steps.append(("pause", float(m.group(1)), VOICES[current_label]))
        elif m.group(2) is not None:
            matched = find_voice_label(m.group(2))
            if matched:
                current_label = matched

        last_end = m.end()

    if last_end < len(text):
        flush_text(text[last_end:], current_label)

    return steps if steps else [("speech", text, VOICES[default_voice_label])]


def parse_voice_label(label):
    """'Urdu (Male) - Asad — Normal/Narration' ko parts mein todta hai (display k liye)."""
    lang_part, rest = label.split(" (", 1)
    gender, rest2 = rest.split(") - ", 1)
    if " — " in rest2:
        name, style = rest2.split(" — ", 1)
    else:
        name, style = rest2, ""
    return {"language": lang_part.strip(), "gender": gender.strip(), "name": name.strip(), "style": style.strip()}


VOICE_META = {label: parse_voice_label(label) for label in VOICES}


def get_sample_text(voice_code):
    for prefix, text in SAMPLE_TEXTS.items():
        if voice_code.startswith(prefix):
            return text
    return "This is a sample of this voice."


def chunk_text(text, max_chars=MAX_CHUNK_CHARS):
    sentences = re.split(r"(?<=[۔.!?])\s+", text.strip())
    chunks = []
    current = ""
    for sentence in sentences:
        if not sentence:
            continue
        if len(current) + len(sentence) + 1 <= max_chars:
            current = (current + " " + sentence).strip()
        else:
            if current:
                chunks.append(current)
            if len(sentence) > max_chars:
                for i in range(0, len(sentence), max_chars):
                    chunks.append(sentence[i:i + max_chars])
                current = ""
            else:
                current = sentence
    if current:
        chunks.append(current)
    return chunks if chunks else [text]


async def _edge_tts_generate(text, voice, rate, filename, volume="+0%", pitch="+0Hz"):
    communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume, pitch=pitch)
    await communicate.save(filename)


def generate_speech(text, voice_label, speed_percent, pitch_hz, volume_percent, progress_callback=None):
    rate = f"{speed_percent:+d}%"
    pitch = f"{pitch_hz:+d}Hz"
    volume = f"{volume_percent:+d}%"

    steps = parse_script(text, voice_label)
    temp_files = []
    total = len(steps)
    try:
        for idx, step in enumerate(steps, start=1):
            kind, content, voice_code = step
            if progress_callback:
                progress_callback(idx / total, f"{'Pause' if kind == 'pause' else 'Awaz'}: Part {idx} of {total}")

            fd, temp_path = tempfile.mkstemp(suffix=".mp3")
            os.close(fd)
            temp_files.append(temp_path)

            if kind == "pause":
                seconds = content
                filler_words = max(1, int(seconds * 3))
                filler_text = "hm " * filler_words
                asyncio.run(_edge_tts_generate(filler_text, voice_code, "+0%", temp_path, volume="-100%"))
            else:
                asyncio.run(_edge_tts_generate(content, voice_code, rate, temp_path, volume=volume, pitch=pitch))

        fd, out_path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        with open(out_path, "wb") as outfile:
            for temp_path in temp_files:
                with open(temp_path, "rb") as infile:
                    outfile.write(infile.read())
        return out_path
    finally:
        for temp_path in temp_files:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass


def preview_voice(voice_label, user_text=""):
    voice = VOICES[voice_label]
    # Agar user ne apna text likha hai to wohi preview mein bolwayen (pehla ~200 characters),
    # taake pata chale unka apna content is voice mein kaisa sunai dega
    clean_text = user_text.strip() if user_text else ""
    if clean_text:
        sample_text = clean_text[:200]
    else:
        sample_text = get_sample_text(voice)
    fd, temp_path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    asyncio.run(_edge_tts_generate(sample_text, voice, "+0%", temp_path))
    return temp_path


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Zee Free Voice Generator", page_icon="🎙️", layout="wide")

st.title("🎙️ Zee Free Voice Generator")
st.caption("Urdu / Hindi / English — Unlimited & Free")

st.markdown(
    """
    <style>
    div.stButton > button {
        border-radius: 50px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if "selected_voice" not in st.session_state:
    st.session_state.selected_voice = list(VOICES.keys())[0]

if "history" not in st.session_state:
    st.session_state.history = []

if "preview_cache" not in st.session_state:
    st.session_state.preview_cache = {}

voice_label = st.session_state.selected_voice

# ---------------------------------------------------------------------------
# Text input (left) + Generated Audios history (right) - jaisy reference design mein tha
# ---------------------------------------------------------------------------
input_col, history_col = st.columns([3, 2])

with input_col:
    st.subheader("📝 Input Text")
    text_input = st.text_area(
        "Apna text yahan likhein",
        height=250,
        placeholder="Yahan apna Urdu, Hindi ya English text likhein...",
        label_visibility="collapsed",
    )
    st.caption(
        "💡 `[pause:2]` = 2 second ka pause  •  `[voice:Guy]` = beech script mein voice badlein"
    )

    # Live stats: word count, character count, estimated duration - text box ke sath hi
    word_count = len(text_input.split()) if text_input.strip() else 0
    char_count = len(text_input)
    # Andaza: normal speed per ~150 alfaz/minute bolti hain voices
    est_seconds = (word_count / 150) * 60 if word_count else 0
    est_minutes = int(est_seconds // 60)
    est_secs_remainder = int(est_seconds % 60)

    stat1, stat2, stat3 = st.columns(3)
    stat1.metric("Words", word_count)
    stat2.metric("Characters", char_count)
    stat3.metric("Andazan Duration", f"{est_minutes}:{est_secs_remainder:02d}")

    with st.expander("⚙️ Advanced Controls", expanded=False):
        speed_percent = st.slider("Speed (%)", min_value=-50, max_value=100, value=0, step=5)
        pitch_hz = st.slider("Pitch (Hz)", min_value=-50, max_value=50, value=0, step=5)
        volume_percent = st.slider("Volume (%)", min_value=-50, max_value=50, value=0, step=5)

    st.caption(f"Selected voice: **{VOICE_META[voice_label]['name']}** ({VOICE_META[voice_label]['language']})")

    if st.button("🔊 Generate Voice", type="primary", use_container_width=True):
        if not text_input.strip():
            st.warning("Pehle kuch text likhein.")
        else:
            progress_bar = st.progress(0, text="Shuru ho raha hai...")

            def update_progress(fraction, label):
                progress_bar.progress(fraction, text=f"{label}  ({int(fraction * 100)}%)")

            try:
                out_path = generate_speech(
                    text_input, voice_label, speed_percent, pitch_hz, volume_percent, update_progress
                )
            except Exception as e:
                progress_bar.empty()
                st.error(
                    "⚠️ Awaz generate nahi ho saki. Yeh voice service ki taraf se temporary "
                    "masla ho sakta hai — internet connection check karein, ya thori dair "
                    "baad dobara try karein."
                )
                st.caption(f"Technical detail: {e}")
                out_path = None

            if out_path:
                progress_bar.empty()

                with open(out_path, "rb") as f:
                    audio_bytes = f.read()
                os.remove(out_path)

                meta = VOICE_META[voice_label]
                st.session_state.history.insert(0, {
                    "id": uuid.uuid4().hex[:8],
                    "text": text_input,
                    "voice_name": meta["name"],
                    "language": meta["language"],
                    "gender": meta["gender"],
                    "timestamp": datetime.now().strftime("%b %d, %Y, %I:%M:%S %p"),
                    "audio_bytes": audio_bytes,
                })
                st.rerun()

with history_col:
    st.subheader("🗂️ Generated Audios")
    if not st.session_state.history:
        st.caption("Abhi tak koi audio generate nahi hui — text likh kar 'Generate Voice' per click karein.")
    else:
        for entry in st.session_state.history:
            with st.container(border=True):
                preview_text = entry["text"][:120] + ("..." if len(entry["text"]) > 120 else "")
                st.markdown(f"{preview_text}")
                st.caption(
                    f"🎙️ {entry['voice_name']}   `{entry['language']}`   `{entry['gender']}`   🕒 {entry['timestamp']}"
                )
                st.audio(entry["audio_bytes"], format="audio/mp3")
                dl_col, del_col = st.columns(2)
                with dl_col:
                    st.download_button(
                        "⬇️ Download",
                        entry["audio_bytes"],
                        file_name=f"voice_{entry['id']}.mp3",
                        mime="audio/mp3",
                        key=f"dl_{entry['id']}",
                        use_container_width=True,
                    )
                with del_col:
                    if st.button("🗑️ Delete", key=f"del_{entry['id']}", use_container_width=True):
                        st.session_state.history = [
                            e for e in st.session_state.history if e["id"] != entry["id"]
                        ]
                        st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Voice selection - searchable cards with tags (Speechma-style)
# Card per click = voice select. "▶" button = sirf play/pause (persistent player).
# ---------------------------------------------------------------------------
st.subheader("🎭 Voice Chunein")

filter_col1, filter_col2, filter_col3 = st.columns([2, 1, 1])
with filter_col1:
    search_query = st.text_input(
        "🔍 Voice search karein", placeholder="jaise: Asad, Storytelling, Deep..."
    )
with filter_col2:
    languages = ["All Languages"] + sorted({meta["language"] for meta in VOICE_META.values()})
    language_filter = st.selectbox("Language", languages)
with filter_col3:
    genders = ["All Genders"] + sorted({meta["gender"] for meta in VOICE_META.values()})
    gender_filter = st.selectbox("Gender", genders)

filtered_voices = list(VOICES.keys())
if search_query:
    filtered_voices = [l for l in filtered_voices if search_query.lower() in l.lower()]
if language_filter != "All Languages":
    filtered_voices = [l for l in filtered_voices if VOICE_META[l]["language"] == language_filter]
if gender_filter != "All Genders":
    filtered_voices = [l for l in filtered_voices if VOICE_META[l]["gender"] == gender_filter]

if not filtered_voices:
    st.info("Koi voice in filters se nahi mili — filter badal kar dekhein.")
else:
    cols = st.columns(3)
    for i, label in enumerate(filtered_voices):
        meta = VOICE_META[label]
        with cols[i % 3]:
            with st.container(border=True):
                is_selected = label == st.session_state.selected_voice

                # Card ke naam per click = select (poora card jaisa behavior)
                card_title = f"{'✅ ' if is_selected else ''}{meta['name']}"
                if st.button(card_title, key=f"select_{label}", use_container_width=True):
                    st.session_state.selected_voice = label
                    st.rerun()

                st.caption(f"`{meta['gender']}`  `{meta['language']}`  `{meta['style']}`")

                # "▶" sirf preview generate/cache karta hai - audio player khud play/pause control deta hai
                if st.button("▶ Sunein", key=f"gen_{label}", use_container_width=True):
                    try:
                        with st.spinner("Loading..."):
                            p = preview_voice(label)
                        with open(p, "rb") as f:
                            st.session_state.preview_cache[label] = f.read()
                        os.remove(p)
                    except Exception:
                        st.error("⚠️ Preview nahi ban saka. Internet check karein ya dobara try karein.")

                if label in st.session_state.preview_cache:
                    st.audio(st.session_state.preview_cache[label], format="audio/mp3")
