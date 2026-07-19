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

if "selected_voice" not in st.session_state:
    st.session_state.selected_voice = list(VOICES.keys())[0]

# ---------------------------------------------------------------------------
# Voice selection - searchable cards
# ---------------------------------------------------------------------------
st.subheader("🎭 Voice Chunein")
search_query = st.text_input(
    "🔍 Voice search karein", placeholder="jaise: Urdu, Male, Female, Storytelling, Deep, Guy..."
)

if search_query:
    filtered_voices = [label for label in VOICES if search_query.lower() in label.lower()]
else:
    filtered_voices = list(VOICES.keys())

if not filtered_voices:
    st.info("Koi voice is naam/keyword se nahi mili — doosra keyword try karein.")
else:
    cols = st.columns(3)
    for i, label in enumerate(filtered_voices):
        with cols[i % 3]:
            with st.container(border=True):
                is_selected = label == st.session_state.selected_voice
                st.markdown(f"**{'✅ ' if is_selected else ''}{label}**")
                btn_cols = st.columns([1, 1])
                with btn_cols[0]:
                    if st.button(
                        "Selected" if is_selected else "Select",
                        key=f"select_{label}",
                        disabled=is_selected,
                        use_container_width=True,
                    ):
                        st.session_state.selected_voice = label
                        st.rerun()
                with btn_cols[1]:
                    if st.button("🔈", key=f"preview_{label}", use_container_width=True, help="Is voice ka sample sunein"):
                        with st.spinner("Loading..."):
                            p = preview_voice(label)
                        st.audio(p)
                        os.remove(p)

voice_label = st.session_state.selected_voice
st.caption(f"Ab select ki hui voice: **{voice_label}**")

st.divider()

col1, col2 = st.columns([2, 1])

with col1:
    text_input = st.text_area(
        "Apna text yahan likhein",
        height=250,
        placeholder="Yahan apna Urdu, Hindi ya English text likhein...",
    )
    st.caption(
        "💡 `[pause:2]` = 2 second ka pause  •  `[voice:Guy]` = beech script mein voice badlein"
    )

    # Live stats: word count, character count, estimated duration
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

with col2:
    if st.button("🔈 Sunein (Apna Text Preview)"):
        with st.spinner("Preview ban raha hai..."):
            preview_path = preview_voice(voice_label, text_input)
        st.audio(preview_path)
        os.remove(preview_path)
    st.caption("Ap ka likha hua text bolegi (pehle 200 characters). Khali chorne per generic sample sunayi degi.")

    with st.expander("⚙️ Advanced Controls", expanded=False):
        speed_percent = st.slider("Speed (%)", min_value=-50, max_value=100, value=0, step=5)
        pitch_hz = st.slider("Pitch (Hz)", min_value=-50, max_value=50, value=0, step=5)
        volume_percent = st.slider("Volume (%)", min_value=-50, max_value=50, value=0, step=5)

st.divider()

if st.button("🔊 Generate Voice", type="primary"):
    if not text_input.strip():
        st.warning("Pehle kuch text likhein.")
    else:
        progress_bar = st.progress(0, text="Shuru ho raha hai...")

        def update_progress(fraction, label):
            progress_bar.progress(fraction, text=f"{label}  ({int(fraction * 100)}%)")

        out_path = generate_speech(
            text_input, voice_label, speed_percent, pitch_hz, volume_percent, update_progress
        )
        progress_bar.empty()

        st.success("Awaz ban gayi hai!")
        with open(out_path, "rb") as f:
            audio_bytes = f.read()
        st.audio(audio_bytes, format="audio/mp3")
        st.download_button("💾 Download MP3", audio_bytes, file_name="voice_output.mp3", mime="audio/mp3")
        os.remove(out_path)
