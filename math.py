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

# -----------------------------
# 1. CONFIG & SESSION STATE
# -----------------------------
st.set_page_config(layout="wide", page_title="Socratic Math Tutor")

I18N = {
    "English": {
        "tool_pen": "Pen",
        "tool_eraser": "Eraser",
        "check_work": "Check my work",
        "teach_me": "Teach me (Full Strategy)",
        "give_hint": "Give me a hint",
        "chat_placeholder": "Tell me what you're thinking...",
        "parent_dash": "👨‍👩‍👧 Parent Dashboard",
    },
    "Deutsch": {
        "tool_pen": "Stift",
        "tool_eraser": "Radiergummi",
        "check_work": "Meine Arbeit prüfen",
        "teach_me": "Lösungsweg erklären",
        "give_hint": "Gib mir einen Hinweis",
        "chat_placeholder": "Schreib mir, was du denkst...",
        "parent_dash": "👨‍👩‍👧 Eltern-Dashboard",
    }
}

for key, default in [
    ("authenticated", False), ("user_id", "guest_user"), 
    ("canvas_version", 0), ("chat", []), ("tool", "pen")
]:
    if key not in st.session_state: st.session_state[key] = default

supabase: Client = create_client("https://kztiarfkgvwyxqzfnwfk.supabase.co", st.secrets["SUPABASE_API_KEY"])
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# -----------------------------
# 2. PROMPTS & HELPERS
# -----------------------------
TUTOR_SYSTEM_PROMPT = "You are a Socratic math tutor. Respond in {language}. NO LaTeX. Use plain text math (x^2, 1/2, sqrt)."
TEACH_PROMPT = "Explain the full strategy to solve this step-by-step. NO LaTeX. Use plain text math."
HINT_PROMPT = "Provide only ONE small next step or a guiding question. Do not solve it. NO LaTeX."
CHECK_PROMPT = "If correct, say 'Perfect!'. If wrong, point out the error step in plain text. NO LaTeX."

def sanitize_math_output(text):
    text = re.sub(r'\\\(|\\\)|\\\[|\\\]', '', text)
    replacements = {"\\times": "*", "\\div": "/", "\\pm": "+/-", "\\approx": "≈", "\\cdot": "*"}
    for latex, plain in replacements.items(): text = text.replace(latex, plain)
    return re.sub(r'\\[a-zA-Z]+', '', text)

def save_event(action):
    try:
        supabase.table("student_progress").insert({
            "user_id": st.session_state.user_id,
            "action_type": action,
            "layer_name": "Main Workspace" # Default since layers are removed
        }).execute()
    except Exception: pass

def display_parent_report(user_id):
    st.markdown("### 📈 Progress Report")
    res = supabase.table("student_progress").select("*").eq("user_id", user_id).execute()
    if not res.data:
        st.info("No data yet.")
        return
    df = pd.DataFrame(res.data)
    total = len(df)
    auto = len(df[df['action_type'] == 'check_work'])
    mastery = auto / total if total > 0 else 0
    st.write(f"**Mastery Score: {int(mastery * 100)}%**")
    st.progress(mastery)

def get_cropped_image(canvas_result):
    if canvas_result.json_data:
        objects = canvas_result.json_data.get("objects", [])
        rects = [obj for obj in objects if obj['type'] == 'rect']
        if rects:
            r = rects[-1]
            img = Image.fromarray(canvas_result.image_data.astype("uint8"))
            return img.crop((r['left'], r['top'], r['left'] + r['width'], r['top'] + r['height']))
    return Image.fromarray(canvas_result.image_data.astype("uint8"))

def image_to_latex(img_data):
    if img_data is None: return ""
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
            temperature=0.2, max_tokens=300
        )
        return sanitize_math_output(res.choices[0].message.content)
    except Exception as e: return f"Tutor Error: {e}"

# -----------------------------
# 3. AUTH & SIDEBAR
# -----------------------------
if not st.session_state.authenticated:
    st.title("Math Tutor Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Log In"):
        try:
            res = supabase.auth.sign_in_with_password({"email": email, "password": password})
            st.session_state.user_id, st.session_state.authenticated = res.user.id, True
            st.rerun()
        except: st.error("Invalid Login")
    st.stop()

with st.sidebar:
    selected_lang = st.selectbox("🌍 Language", ["English", "Deutsch"])
    texts = I18N[selected_lang]
    if st.button(f"✏️ {texts['tool_pen']}"): st.session_state.tool = "pen"
    if st.button(f"🧽 {texts['tool_eraser']}"): st.session_state.tool = "eraser"
    if st.button("🔍 Focus Tool"): st.session_state.tool = "rect"
    if st.button("🗑️ Clear Canvas"):
        st.session_state.canvas_version += 1
        st.rerun()
    st.divider()
    if st.checkbox(texts["parent_dash"]):
        display_parent_report(st.session_state.user_id)

# -----------------------------
# 4. CANVAS & ACTION BUTTONS
# -----------------------------
st.header("Math Workspace")

canvas_result = st_canvas(
    stroke_width=3 if st.session_state.tool == "pen" else 40,
    stroke_color="#000000" if st.session_state.tool != "eraser" else "#FFFFFF",
    background_color="#FFFFFF",
    height=4000, width=1100, 
    drawing_mode="freedraw" if st.session_state.tool != "rect" else "rect",
    key=f"canvas_{st.session_state.canvas_version}"
)

col1, col2, col3 = st.columns(3)

if canvas_result.image_data is not None:
    with col1:
        if st.button(texts["check_work"]):
            latex = image_to_latex(get_cropped_image(canvas_result))
            if latex:
                save_event("check_work")
                st.session_state.feedback = ai_call(CHECK_PROMPT, latex)
    with col2:
        if st.button(texts["give_hint"]):
            latex = image_to_latex(get_cropped_image(canvas_result))
            if latex:
                save_event("hint")
                st.session_state.feedback = ai_call(HINT_PROMPT, latex)
    with col3:
        if st.button(texts["teach_me"]):
            latex = image_to_latex(get_cropped_image(canvas_result))
            if latex:
                save_event("teach_me")
                st.session_state.feedback = ai_call(TEACH_PROMPT, latex)

# -----------------------------
# 5. DISPLAY & CHAT
# -----------------------------
if "feedback" in st.session_state:
    st.info(st.session_state.feedback)

st.divider()
chat_input = st.chat_input(texts["chat_placeholder"])
if chat_input:
    reply = ai_call(TUTOR_SYSTEM_PROMPT.format(language=selected_lang), chat_input)
    st.session_state.chat.append({"role": "user", "content": chat_input})
    st.session_state.chat.append({"role": "assistant", "content": reply})

for msg in st.session_state.chat:
    with st.chat_message(msg["role"]): st.write(msg["content"])