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

# -----------------------------
# 1. CONFIG & TRANSLATIONS
# -----------------------------
ACCESS_CODE = "1a2b3c!8"

# Λεξικό Μεταφράσεων
I18N = {
    "English": {
        "enter_code": "Enter access code",
        "choose_layer": "Choose Layer",
        "canvas_instr": "Write your own exercises on the canvas and solve them.",
        "canvas_help": "If something feels wrong or confusing, talk to me below.",
        "tool_pen": "Pen",
        "tool_eraser": "Eraser",
        "check_work": "Check my work",
        "teach_me": "Teach me how to solve this",
        "month_review": "Month Review",
        "month_review_sub": "📅 Monthly Revision",
        "tutor_thinking": "Thinking carefully...",
        "tutor_note": "### Tutor’s note",
        "how_to_solve": "### How to approach this problem",
        "no_data": "Not enough data for this month yet!",
        "chat_placeholder": "Tell me what you're thinking...",
        "lang_name": "English"
    },
    "Deutsch": {
        "enter_code": "Zugangscode eingeben",
        "choose_layer": "Ebene auswählen",
        "canvas_instr": "Schreibe deine eigenen Übungen auf die Leinwand und löse sie.",
        "canvas_help": "Wenn sich etwas falsch anfühlt, sprich unten mit mir.",
        "tool_pen": "Stift",
        "tool_eraser": "Radiergummi",
        "check_work": "Meine Arbeit prüfen",
        "teach_me": "Erkläre mir den Weg",
        "month_review": "Monatsrückblick",
        "month_review_sub": "📅 Monatliche Wiederholung",
        "tutor_thinking": "Ich denke nach...",
        "tutor_note": "### Notiz des Tutors",
        "how_to_solve": "### Lösungsweg",
        "no_data": "Noch nicht genügend Daten für diesen Monat vorhanden!",
        "chat_placeholder": "Schreib mir, was du denkst...",
        "lang_name": "Deutsch"
    }
}

# -----------------------------
# 2. SESSION STATE INIT
# -----------------------------
if "user_id" not in st.session_state:
    st.session_state.user_id = "guest_user"
if "canvas_version" not in st.session_state:
    st.session_state.canvas_version = 0
if "chat" not in st.session_state:
    st.session_state.chat = []
if "tool" not in st.session_state:
    st.session_state.tool = "pen"

# -----------------------------
# 3. AUTHENTICATION & UI SETUP
# -----------------------------
st.set_page_config(layout="wide", page_title="Socratic Math Tutor")

st.markdown(
    """
    <style>
        /* Μειώνει το πλάτος του sidebar */
        [data-testid="stSidebar"] {
            min-width: 200px;
            max-width: 200px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# Sidebar - Language Selection
with st.sidebar:
    selected_lang = st.selectbox("🌍 Language / Sprache", ["English", "Deutsch"])
    texts = I18N[selected_lang]
    
    st.divider()
    if st.button(f"✏️ {texts['tool_pen']}"):
        st.session_state.tool = "pen"
    if st.button(f"🧽 {texts['tool_eraser']}"):
        st.session_state.tool = "eraser"
    if st.button("🗑️ Clear Canvas"):
        st.session_state.canvas_version += 1
        st.rerun()


# 1. Αρχικοποίηση της κατάστασης αυθεντικοποίησης
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# 2. Έλεγχος αν ο χρήστης είναι ήδη συνδεδεμένος
if not st.session_state.authenticated:
    code = st.text_input("Enter access code", type="password")
    if code == ACCESS_CODE:
        st.session_state.authenticated = True
        st.rerun() # Επανεκκίνηση για να εξαφανιστεί το πεδίο του κωδικού
    else:
        if code: # Αν έγραψε κάτι και είναι λάθος
            st.error("Wrong code!")
        st.stop() # Σταμάτημα του script μέχρι να δοθεί σωστός κωδικός

# -----------------------------
# 4. API CLIENTS & PROMPTS
# -----------------------------
client = OpenAI(api_key=st.secrets["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
supabase: Client = create_client("https://kztiarfkgvwyxqzfnwfk.supabase.co", st.secrets["SUPABASE_API_KEY"])

TUTOR_SYSTEM_PROMPT = """
You are a calm and experienced mathematics tutor. You act like a Socratic teacher.
- Never give the full answer immediately.
- Use short math-style phrases.
- Use $...$ for inline math and $$...$$ for blocks.
- Respond strictly in {language}.

Formatting Rules:
- ALWAYS use LaTeX for any mathematical expression or symbol.
- Use single dollar signs $...$ for inline math (e.g., $x^2$).
- Use double dollar signs $$...$$ for standalone formulas or steps.
- NEVER use plain text symbols like ^, *, or sqrt(). Use \^, \cdot, and \sqrt instead.
- If you mention a variable like 'x', wrap it in dollars: $x$.
"""

# -----------------------------
# 5. HELPER FUNCTIONS
# -----------------------------
def save_event(action, layer, tags=[]):
    try:
        supabase.table("student_progress").insert({
            "user_id": st.session_state.user_id,
            "layer_name": layer,
            "action_type": action,
            "topic_tags": tags,
            "created_at": datetime.now().isoformat()
        }).execute()
    except Exception as e:
        st.error(f"DB Error: {e}")

def ai_call(system_prompt, user_content, max_tokens=600):
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt.format(language=texts['lang_name'])},
            {"role": "user", "content": user_content}
        ],
        temperature=0.3,
        max_tokens=max_tokens
    )
    return response.choices[0].message.content.strip()

def image_to_latex(image_data):
    if image_data is None: return ""
    image = Image.fromarray(image_data.astype("uint8"))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    img_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    response = requests.post(
        "https://api.mathpix.com/v3/text",
        headers={"app_id": st.secrets["MATHPIX_APP_ID"], "app_key": st.secrets["MATHPIX_APP_KEY"]},
        json={"src": f"data:image/png;base64,{img_base64}", "formats": ["latex_styled"]}
    )
    return response.json().get("latex_styled", "") if response.status_code == 200 else ""

# -----------------------------
# 6. MAIN APP INTERFACE
# -----------------------------
layers = ["Layer 1: Fractions, Decimals", "Layer 2: Identities", "Layer 3: Functions"] # Συντόμευση για το παράδειγμα
chosen_layer = st.selectbox(texts["choose_layer"], layers)

# 2. Πρόσθεσε εδώ το "Interactive" κομμάτι
if "Layer 4: Graphs of functions" in chosen_layer:
    st.divider() # Μια γραμμή για να ξεχωρίζει από τον καμβά
    st.subheader("📊 Interactive Function Explorer")
    
    # Sliders για τις παραμέτρους (α, c)
    col1, col2 = st.columns(2)
    with col1:
        a = st.slider("Παράμετρος a (Κλίση/Άνοιγμα):", -5.0, 5.0, 1.0)
    with col2:
        c = st.slider("Παράμετρος c (Μετατόπιση y):", -10.0, 10.0, 0.0)
    
    # Υπολογισμός και Γράφημα
    x = np.linspace(-10, 10, 400)
    y = a * x**2 + c # Παράδειγμα για παραβολή
    
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(x, y, label=f"$y = {a}x^2 + {c}$", color='red')
    ax.axhline(0, color='black', lw=1)
    ax.axvline(0, color='black', lw=1)
    ax.set_ylim(-20, 20)
    ax.grid(True, alpha=0.3)
    ax.legend()
    
    st.pyplot(fig)
    st.divider()
st.header(chosen_layer)
st.write(texts["canvas_instr"])

# Canvas Logic
stroke_color = "#000000" if st.session_state.tool == "pen" else "#FFFFFF"
stroke_width = 3 if st.session_state.tool == "pen" else 30
with st.container():
    canvas_result = st_canvas(
    stroke_width=stroke_width,
    stroke_color=stroke_color,
    background_color="#FFFFFF",
    height=6000,
    width=1200,
    drawing_mode="freedraw",
    key=f"canvas_{st.session_state.canvas_version}",
)

# Buttons Row
col1, col2, col3 = st.columns(3)

with col1:
    if st.button(texts["check_work"]):
        latex = image_to_latex(canvas_result.image_data)
        if latex:
            save_event("check_work", chosen_layer)
            with st.spinner(texts["tutor_thinking"]):
                feedback = ai_call(TUTOR_SYSTEM_PROMPT, f"Check this: {latex}")
                st.session_state.tutor_feedback = feedback
                st.session_state.last_latex = latex

with col2:
    if st.button(texts["teach_me"]):
        latex = image_to_latex(canvas_result.image_data)
        if latex:
            # AI Tagging
            tags_res = ai_call("Return only 2-3 math tags separated by comma.", f"Tag this: {latex}")
            tags = [t.strip() for t in tags_res.split(",")]
            save_event("teach_me", chosen_layer, tags=tags)
            
            with st.spinner(texts["tutor_thinking"]):
                methodology = ai_call(TUTOR_SYSTEM_PROMPT, f"Explain methodology for: {latex}")
                st.session_state.methodology = methodology
                st.session_state.last_latex = latex

with col3:
    if st.button(texts["month_review"]):
        # Εδώ καλείται η generate_monthly_revision
        pass

# -----------------------------
# 7. DISPLAY RESULTS
# -----------------------------
if "last_latex" in st.session_state:
    st.latex(st.session_state.last_latex)

if "tutor_feedback" in st.session_state:
    st.info(f"{texts['tutor_note']}\n\n{st.session_state.tutor_feedback}")

if "methodology" in st.session_state:
    st.success(f"{texts['how_to_solve']}\n\n{st.session_state.methodology}")

# Chat Interface
st.divider()
user_input = st.chat_input(texts["chat_placeholder"])
if user_input:
    st.session_state.chat.append({"role": "user", "content": user_input})
    response = ai_call(TUTOR_SYSTEM_PROMPT, user_input)
    st.session_state.chat.append({"role": "assistant", "content": response})
    st.rerun()

for msg in st.session_state.chat:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])