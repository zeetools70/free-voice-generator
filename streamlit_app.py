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
    "English US (Male) - Guy — Narration/News": "en-US-GuyNeural",
    "English US (Male) - Roger — Deep/Documentary": "en-US-RogerNeural",
    "English US (Male) - Christopher — Deep/Authoritative": "en-US-ChristopherNeural",
    "English US (Male) - Andrew — Warm/Confident Narration": "en-US-AndrewNeural",
    "English UK (Female) - Sonia — Calm/Professional": "en-GB-SoniaNeural",
    "English UK (Male) - Ryan — Narration/Formal": "en-GB-RyanNeural",
}

SAMPLE_TEXTS = {
    "ur-PK": "Yeh awaz ka namoona hai. Umeed hai apko pasand ayegi.",
    "hi-IN": "Yeh awaz ka namoona hai. Umeed hai aapko pasand aayegi.",
    "en-US": "This is a sample of this voice. I hope you like how it sounds.",
    "en-GB": "This is a sample of this voice. I hope you like how it sounds.",
}

MAX_CHUNK_CHARS = 1500
PAUSE_PATTERN = re.compile(r"\[pause:\s*(\d+(?:\.\d+)?)\s*\]", re.IGNORECASE)
RATE_MAP = {"Slow": "-20%", "Normal": "+0%", "Fast": "+25%"}


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


def split_with_pauses(text):
    parts = []
    last_end = 0
    for m in PAUSE_PATTERN.finditer(text):
        if m.start() > last_end:
            parts.append(("text", text[last_end:m.start()]))
        parts.append(("pause", float(m.group(1))))
        last_end = m.end()
    if last_end < len(text):
        parts.append(("text", text[last_end:]))
    return parts if parts else [("text", text)]


async def _edge_tts_generate(text, voice, rate, filename, volume="+0%"):
    communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
    await communicate.save(filename)


def generate_speech(text, voice_label, speed, progress_callback=None):
    voice = VOICES[voice_label]
    rate = RATE_MAP[speed]

    segments = split_with_pauses(text)
    steps = []
    for kind, content in segments:
        if kind == "pause":
            steps.append(("pause", content))
        else:
            for chunk in chunk_text(content):
                if chunk.strip():
                    steps.append(("speech", chunk))

    temp_files = []
    total = len(steps)
    try:
        for idx, (kind, content) in enumerate(steps, start=1):
            if progress_callback:
                progress_callback(idx / total, f"{'Pause' if kind == 'pause' else 'Awaz'}: Part {idx} of {total}")

            fd, temp_path = tempfile.mkstemp(suffix=".mp3")
            os.close(fd)
            temp_files.append(temp_path)

            if kind == "pause":
                filler_words = max(1, int(content * 3))
                filler_text = "hm " * filler_words
                asyncio.run(_edge_tts_generate(filler_text, voice, "+0%", temp_path, volume="-100%"))
            else:
                asyncio.run(_edge_tts_generate(content, voice, rate, temp_path))

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


def preview_voice(voice_label):
    voice = VOICES[voice_label]
    sample_text = get_sample_text(voice)
    fd, temp_path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    asyncio.run(_edge_tts_generate(sample_text, voice, "+0%", temp_path))
    return temp_path


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Voice Generator", page_icon="🎙️", layout="wide")

st.title("🎙️ Voice Generator")
st.caption("Urdu / Hindi / English — Unlimited & Free")

col1, col2 = st.columns([2, 1])

with col1:
    text_input = st.text_area(
        "Apna text yahan likhein",
        height=250,
        placeholder="Yahan apna Urdu, Hindi ya English text likhein... Pause ke liye [pause:2] likhein",
    )

with col2:
    voice_label = st.selectbox("Voice chunein", list(VOICES.keys()))
    speed = st.selectbox("Speed", ["Slow", "Normal", "Fast"], index=1)

    if st.button("🔈 Sunein (Preview)"):
        with st.spinner("Preview ban raha hai..."):
            preview_path = preview_voice(voice_label)
        st.audio(preview_path)
        os.remove(preview_path)

st.divider()

if st.button("🔊 Generate Voice", type="primary"):
    if not text_input.strip():
        st.warning("Pehle kuch text likhein.")
    else:
        progress_bar = st.progress(0, text="Shuru ho raha hai...")

        def update_progress(fraction, label):
            progress_bar.progress(fraction, text=label)

        out_path = generate_speech(text_input, voice_label, speed, update_progress)
        progress_bar.empty()

        st.success("Awaz ban gayi hai!")
        with open(out_path, "rb") as f:
            audio_bytes = f.read()
        st.audio(audio_bytes, format="audio/mp3")
        st.download_button("💾 Download MP3", audio_bytes, file_name="voice_output.mp3", mime="audio/mp3")
        os.remove(out_path)
