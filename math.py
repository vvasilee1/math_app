import streamlit as st
from streamlit_drawable_canvas import st_canvas
from supabase import create_client, Client
from openai import OpenAI
from PIL import Image
import numpy as np
import io
import base64
import requests
import pandas as pd
import re
import matplotlib.pyplot as plt

# -----------------------------
# 1. CONFIG & TRANSLATIONS
# -----------------------------
st.set_page_config(layout="wide", page_title="Socratic Math Tutor")

I18N = {
    "English": {
        "choose_layer": "Choose Layer",
        "tool_pen": "Pen",
        "tool_eraser": "Eraser",
        "check_work": "Check my work",
        "teach_me": "Teach me how to solve this",
        "chat_placeholder": "Tell me what you're thinking...",
        "lang_name": "English"
    },
    "Deutsch": {
        "choose_layer": "Ebene auswählen",
        "tool_pen": "Stift",
        "tool_eraser": "Radiergummi",
        "check_work": "Meine Arbeit prüfen",
        "teach_me": "Erkläre mir den Weg",
        "chat_placeholder": "Schreib mir, was du denkst...",
        "lang_name": "Deutsch"
    }
}

# -----------------------------
# 2. SESSION STATE INIT
# -----------------------------
for key, default in [
    ("authenticated", False), ("user_id", "guest_user"), 
    ("canvas_version", 0), ("chat", []), ("tool", "pen")
]:
    if key not in st.session_state: st.session_state[key] = default

supabase: Client = create_client("https://kztiarfkgvwyxqzfnwfk.supabase.co", st.secrets["SUPABASE_API_KEY"])
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# -----------------------------
# 3. HELPERS & PROMPTS
# -----------------------------
TUTOR_SYSTEM_PROMPT = "You are a Socratic math tutor. Respond in {language}. No LaTeX. Use plain text math (x^2, 1/2, sqrt)."
TEACH_PROMPT = "Socratic mode: Don't solve. Ask one guiding question. No LaTeX."
CHECK_PROMPT = "If correct, say 'Perfect!'. If wrong, point out the error step in plain text. No LaTeX."

def sanitize_math_output(text):
    text = re.sub(r'\\\(|\\\)|\\\[|\\\]', '', text)
    replacements = {"\\times": "*", "\\div": "/", "\\pm": "+/-", "\\approx": "≈"}
    for latex, plain in replacements.items(): text = text.replace(latex, plain)
    return re.sub(r'\\[a-zA-Z]+', '', text)

def get_cropped_image(canvas_result):
    if canvas_result.json_data:
        rects = [obj for obj in canvas_result.json_data.get("objects", []) if obj['type'] == 'rect']
        if rects:
            r = rects[-1]
            img = Image.fromarray(canvas_result.image_data.astype("uint8"))
            return img.crop((r['left'], r['top'], r['left'] + r['width'], r['top'] + r['height']))
    return Image.fromarray(canvas_result.image_data.astype("uint8"))

def image_to_latex(img_data):
    if img_data is None: return ""
    # Process either numpy array from canvas or PIL image from uploader
    img = Image.fromarray(img_data.astype("uint8")) if isinstance(img_data, np.ndarray) else img_data
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    img_b64 = base64.b64encode(buffer.getvalue()).decode()
    
    res = requests.post("https://api.mathpix.com/v3/text",
        headers={"app_id": st.secrets["MATHPIX_APP_ID"], "app_key": st.secrets["MATHPIX_APP_KEY"]},
        json={"src": f"data:image/png;base64,{img_b64}", "formats": ["latex_styled"]})
    return res.json().get("latex_styled", "")

def ai_call(prompt, content):
    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": content}],
            temperature=0.2, max_tokens=250
        )
        return sanitize_math_output(res.choices[0].message.content)
    except Exception as e: return f"Error: {e}"

# -----------------------------
# 4. AUTHENTICATION UI
# -----------------------------
if not st.session_state.authenticated:
    st.title("Socratic Math Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Log In"):
        try:
            res = supabase.auth.sign_in_with_password({"email": email, "password": password})
            st.session_state.user_id, st.session_state.authenticated = res.user.id, True
            st.rerun()
        except: st.error("Invalid credentials.")
    st.stop()

# -----------------------------
# 5. SIDEBAR & TOOLS
# -----------------------------
with st.sidebar:
    selected_lang = st.selectbox("🌍 Language", ["English", "Deutsch"])
    texts = I18N[selected_lang]
    if st.button(f"✏️ {texts['tool_pen']}"): st.session_state.tool = "pen"
    if st.button("🔍 Focus Tool"): st.session_state.tool = "rect"
    if st.button("🗑️ Clear"):
        st.session_state.canvas_version += 1
        st.rerun()

# -----------------------------
# 6. MAIN INTERFACE
# -----------------------------
layers = ["Layer 1: Fractions", "Layer 2: Identities", "Layer 4: Graphs"]
chosen_layer = st.selectbox(texts["choose_layer"], layers)
st.header(chosen_layer)

canvas_result = st_canvas(
    stroke_width=3 if st.session_state.tool == "pen" else 2,
    stroke_color="#000000", background_color="#FFFFFF",
    height=800, width=1000,
    drawing_mode="freedraw" if st.session_state.tool == "pen" else "rect",
    key=f"canvas_{st.session_state.canvas_version}"
)

col1, col2, _ = st.columns([1, 1, 2])
# Processing buttons AFTER canvas definition to avoid AttributeError
if canvas_result.image_data is not None:
    with col1:
        if st.button(texts["check_work"]):
            cropped = get_cropped_image(canvas_result)
            latex = image_to_latex(cropped)
            if latex: st.session_state.feedback = ai_call(CHECK_PROMPT, latex)
    with col2:
        if st.button(texts["teach_me"]):
            cropped = get_cropped_image(canvas_result)
            latex = image_to_latex(cropped)
            if latex: st.session_state.methodology = ai_call(TEACH_PROMPT, latex)

# -----------------------------
# 7. RESULTS & CHAT
# -----------------------------
if "feedback" in st.session_state: st.info(st.session_state.feedback)
if "methodology" in st.session_state: st.success(st.session_state.methodology)

chat_input = st.chat_input(texts["chat_placeholder"])
if chat_input:
    reply = ai_call(TUTOR_SYSTEM_PROMPT.format(language=selected_lang), chat_input)
    st.session_state.chat.append({"role": "assistant", "content": reply})

for msg in st.session_state.chat:
    with st.chat_message(msg["role"]): st.write(msg["content"])




