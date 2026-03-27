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
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import re

# -----------------------------
# 1. CONFIG & TRANSLATIONS
# -----------------------------
ACCESS_CODE = "1a2b3c!8"

I18N = {
    "English": {
        "enter_code": "Enter access code",
        "choose_layer": "Choose Layer",
        "canvas_instr": "Write your exercises on the canvas.",
        "tool_pen": "Pen",
        "tool_eraser": "Eraser",
        "check_work": "Check my work",
        "teach_me": "Teach me how to solve this",
        "month_review": "Month Review",
        "tutor_thinking": "Thinking carefully...",
        "tutor_note": "### Tutor’s note",
        "how_to_solve": "### How to approach this problem",
        "chat_placeholder": "Tell me what you're thinking...",
        "lang_name": "English"
    },
    "Deutsch": {
        "enter_code": "Zugangscode eingeben",
        "choose_layer": "Ebene auswählen",
        "canvas_instr": "Schreibe deine Übungen auf die Leinwand.",
        "tool_pen": "Stift",
        "tool_eraser": "Radiergummi",
        "check_work": "Meine Arbeit prüfen",
        "teach_me": "Erkläre mir den Weg",
        "month_review": "Monatsrückblick",
        "tutor_thinking": "Ich denke nach...",
        "tutor_note": "### Notiz des Tutors",
        "how_to_solve": "### Lösungsweg",
        "chat_placeholder": "Schreib mir, was du denkst...",
        "lang_name": "Deutsch"
    }
}

# -----------------------------
# 2. SESSION STATE INIT
# -----------------------------
if "authenticated" not in st.session_state: st.session_state.authenticated = False
if "user_id" not in st.session_state: st.session_state.user_id = "guest_user"
if "canvas_version" not in st.session_state: st.session_state.canvas_version = 0
if "chat" not in st.session_state: st.session_state.chat = []
if "tool" not in st.session_state: st.session_state.tool = "pen"

supabase: Client = create_client("https://kztiarfkgvwyxqzfnwfk.supabase.co", st.secrets["SUPABASE_API_KEY"])

def display_parent_report(user_id):
    st.markdown("## 📈 Στατιστικά Προόδου (Parent Report)")
    
    # Ανάκτηση δεδομένων από το Supabase
    response = supabase.table("student_progress").select("*").eq("user_id", user_id).execute()
    
    if not response.data:
        st.info("Δεν υπάρχουν ακόμα δεδομένα προόδου.")
        return

    df = pd.DataFrame(response.data)
    
    # Υπολογισμός Mastery Score
    total_actions = len(df)
    autonomous_actions = len(df[df['action_type'] == 'check_work'])
    
    # Ποσοστό προόδου
    progress_percent = (autonomous_actions / total_actions) if total_actions > 0 else 0
    
    # Εμφάνιση Progress Bar
    st.write(f"**Mastery: {int(progress_percent * 100)}%**")
    st.progress(progress_percent)
    
    # Breakdown ανά Layer
    st.markdown("### Ανάπτυξη ανά Ενότητα")
    layer_stats = df.groupby('layer_name')['action_type'].value_counts().unstack().fillna(0)
    for layer in layer_stats.index:
        guided = layer_stats.loc[layer].get('teach_me', 0)
        auto = layer_stats.loc[layer].get('check_work', 0)
        layer_progress = auto / (auto + guided) if (auto + guided) > 0 else 0
        st.write(f"{layer}: {int(layer_progress * 100)}%")
        st.progress(layer_progress)
# -----------------------------
# 3. UI SETUP & AUTH
# -----------------------------
st.set_page_config(layout="wide", page_title="Socratic Math Tutor")

st.markdown("""
    <style>
        [data-testid="stSidebar"] { min-width: 160px; max-width: 160px; }
    </style>
""", unsafe_allow_html=True)

# --- SYSTEM LOGIN / SIGN UP ---
if not st.session_state.authenticated:
    tab1, tab2 = st.tabs(["Login", "Sign Up"])
    
    with tab1:
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.button("Log In"):
            try:
                # Σύνδεση στο Supabase
                res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state.user_id = res.user.id # Το μοναδικό ID του μαθητή
                st.session_state.authenticated = True
                st.rerun()
            except Exception as e:
                st.error("Invalid credentials. Try again!")

    with tab2:
        new_email = st.text_input("New Email")
        new_password = st.text_input("New Password", type="password")
        if st.button("Create Account"):
            try:
                # Εγγραφή νέου χρήστη
                res = supabase.auth.sign_up({"email": new_email, "password": new_password})
                st.success("Account created! You can now log in.")
            except Exception as e:
                st.error(f"Error: {e}")
    st.stop()

with st.sidebar:
    selected_lang = st.selectbox("🌍 Language", ["English", "Deutsch"])
    texts = I18N[selected_lang]
    st.divider()
    if st.button(f"✏️ {texts['tool_pen']}"): st.session_state.tool = "pen"
    if st.button(f"🧽 {texts['tool_eraser']}"): st.session_state.tool = "eraser"
    if st.button("🗑️ Clear"):
        st.session_state.canvas_version += 1
        st.rerun()
    st.divider()
    show_report = st.checkbox("👨‍👩‍👧 Parent Dashboard")

    if show_report:
    # Καλούμε τη συνάρτηση που δημιουργήσαμε
        display_parent_report(st.session_state.user_id)

# -----------------------------
# 4. API & DATABASE
# -----------------------------
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])




TUTOR_SYSTEM_PROMPT = """
You are a Socratic math tutor. Respond strictly in {language}.

MATHEMATICAL OUTPUT RULES:
- NEVER use backslashes (\), curly braces ({ }), or LaTeX commands (e.g., no \frac, no \sqrt).
- Use plain text mathematical notation ONLY.
- Use ^ for exponents (x^2).
- Use / for fractions (1/2).
- Use sqrt() for square roots.
- Use * for multiplication.
- Format equations clearly on their own lines.

Example of allowed style: 
'To solve x^2 = 9, you take the square root of both sides, so x = 3 or x = -3.'
"""
# -----------------------------
# 5. HELPERS
# -----------------------------
def sanitize_math_output(text):
    """
    Removes common LaTeX fragments and converts basic ones 
    to plain text as a safety net.
    """
    # Remove LaTeX delimiters like \( \) or \[ \]
    text = re.sub(r'\\\(|\\\)|\\\[|\\\]', '', text)
    
    # Simple replacements for common symbols if the AI slips up
    replacements = {
        "\\times": "*",
        "\\div": "/",
        "\\pm": "+/-",
        "\\approx": "≈",
        "\\neq": "!=",
        "\\cdot": "*",
    }
    for latex, plain in replacements.items():
        text = text.replace(latex, plain)
        
    # Final pass: remove any remaining backslashes and words attached to them
    # This acts as a 'scorched earth' policy for LaTeX commands
    text = re.sub(r'\\[a-zA-Z]+', '', text)
    
    return text

def clean_text(text):
    text = re.sub(r"\$.*?\$", "", text)  # remove LaTeX blocks
    return text

def save_event(action, layer, tags=[]):
    try:
        supabase.table("student_progress").insert({
            "user_id": st.session_state.user_id,
            "layer_name": layer,
            "action_type": action,
            "topic_tags": tags
        }).execute()
    except Exception: pass

def ai_call(system_prompt, user_content):
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"The student's work/problem is: {user_content}"}
            ],
            temperature=0.2, # Lower temperature = more focused on rules
            max_tokens=250,   # Keeps hints concise and costs low
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Tutor is resting briefly. Error: {e}"

def get_cropped_image(canvas_result):
    """Extracts the bounding box of the last drawn rectangle and crops the image."""
    if canvas_result.json_data is not None:
        objects = canvas_result.json_data.get("objects", [])
        # Find the last 'rect' object drawn by the user
        rects = [obj for obj in objects if obj['type'] == 'rect']
        
        if rects:
            last_rect = rects[-1]
            left = last_rect['left']
            top = last_rect['top']
            width = last_rect['width']
            height = last_rect['height']
            
            # Convert canvas array to PIL Image
            full_img = Image.fromarray(canvas_result.image_data.astype("uint8"))
            
            # Crop using the coordinates (left, top, right, bottom)
            cropped_img = full_img.crop((left, top, left + width, top + height))
            return cropped_img
            
    # Fallback: if no rect found, return the full image (converted to PIL)
    return Image.fromarray(canvas_result.image_data.astype("uint8"))

def image_to_latex(canvas_result):
    if canvas_result.image_data is None: return ""
    
    # Get the focused crop
    image = get_cropped_image(canvas_result)
    
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    img_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    res = requests.post("https://api.mathpix.com/v3/text",
        headers={
            "app_id": st.secrets["MATHPIX_APP_ID"], 
            "app_key": st.secrets["MATHPIX_APP_KEY"]
        },
        json={"src": f"data:image/png;base64,{img_base64}", "formats": ["latex_styled"]})
    
    return res.json().get("latex_styled", "")

# -----------------------------
# 6. MAIN INTERFACE
# -----------------------------
layers = ["Layer 1: Fractions", "Layer 2: Identities", "Layer 4: Graphs of functions"]
chosen_layer = st.selectbox(texts["choose_layer"], layers)

if "Layer 4" in chosen_layer:
    st.subheader("📊 Interactive Function Explorer")
    col1, col2 = st.columns(2)
    with col1: a = st.slider("Parameter a:", -5.0, 5.0, 1.0)
    with col2: c = st.slider("Parameter c:", -10.0, 10.0, 0.0)
    x = np.linspace(-10, 10, 400)
    y = a * x**2 + c
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(x, y, color='red', label=f"$y={a}x^2+{c}$")
    ax.axhline(0, color='black', lw=1); ax.axvline(0, color='black', lw=1)
    ax.grid(True, alpha=0.3); ax.legend()
    st.pyplot(fig)

st.header(chosen_layer)
if st.button("🔍 Focus Tool"): 
    st.session_state.tool = "rect"
canvas_result = st_canvas(
    stroke_width=3 if st.session_state.tool=="pen" else 30,
    stroke_color="#000000" if st.session_state.tool=="pen" else "#FFFFFF",
    background_color="#FFFFFF", height=6000, width=1100,
    drawing_mode="freedraw" if st.session_state.tool == "pen" else "rect"
)
TEACH_PROMPT = """
You are a Socratic Math Tutor. Your goal is to guide the student to the answer without giving it away.

STRICT OUTPUT RULES:
1. NO LATEX: Never use backslashes (\), curly braces ({}), or commands like \frac, \sqrt, or \times.
2. PLAIN MATH ONLY: 
   - Use / for fractions (e.g., 3/4)
   - Use ^ for exponents (e.g., x^2)
   - Use * for multiplication (e.g., 5 * x)
   - Use sqrt() for roots (e.g., sqrt(16))
3. SOCRATIC METHOD: 
   - Identify the student's problem from the provided text.
   - Do not solve it for them.
   - Ask ONE guiding question or provide ONE small hint about the first step.
4. TONE: Encouraging, brief, and clear.

Example of BAD response: "Use the quadratic formula: x = \frac{-b \pm \sqrt{b^2-4ac}}{2a}"
Example of GOOD response: "To start, look at the equation. Can you identify which numbers represent a, b, and c in the standard form ax^2 + bx + c = 0?"
"""
CHECK_PROMPT = """
You are a Math Validator. 
1. If the student's math is 100% correct, reply ONLY with a brief positive acknowledgment like "Perfect!" or "Spot on!"
2. Do NOT suggest alternative methods or 'tutor hints' if the work is correct.
3. If there is an error, briefly point out the specific step where the mistake occurred using PLAIN TEXT MATH (No LaTeX).
"""
col1, col2, col3 = st.columns(3)
with col1:
    if st.button(texts["check_work"]):
        latex = image_to_latex(canvas_result.image_data)
        if latex:
            save_event("check_work", chosen_layer)
            st.session_state.tutor_feedback = clean_text(
                                              ai_call(CHECK_PROMPT, f"{latex}")
                                              )
            st.session_state.last_latex = latex
with col2:
    if st.button(texts["teach_me"]):
        latex = image_to_latex(canvas_result.image_data)
        if latex:
            save_event("teach_me", chosen_layer)
            st.session_state.methodology = ai_call(TEACH_PROMPT,f"{latex}")
            st.session_state.last_latex = latex

uploaded_file = st.file_uploader("📷 Upload your exercise", type=["png", "jpg", "jpeg"])
latex = ""

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    latex = image_to_latex(np.array(image))
elif canvas_result.image_data is not None:
    latex = image_to_latex(canvas_result.image_data)
# -----------------------------
# 7. RESULTS & CHAT
# -----------------------------
#if "last_latex" in st.session_state: st.latex(st.session_state.last_latex)
if "tutor_feedback" in st.session_state:
    clean_feedback = sanitize_math_output(st.session_state.tutor_feedback)
    st.info(clean_feedback)
if "methodology" in st.session_state: st.success(st.session_state.methodology)

st.divider()
user_input = st.chat_input(texts["chat_placeholder"])
if user_input:
    raw_response = ai_call(TUTOR_SYSTEM_PROMPT, user_input)
    clean_response = sanitize_math_output(raw_response)
    st.session_state.chat.append({"role": "assistant", "content": clean_response})

for msg in st.session_state.chat:
    with st.chat_message(msg["role"]): st.write(msg["content"])






