import streamlit as st
from streamlit_drawable_canvas import st_canvas
from openai import OpenAI

# ---------------------------
# Page config
# ---------------------------
st.set_page_config(layout="wide")

# ---------------------------
# Session state initialization
# ---------------------------
if "tool" not in st.session_state:
    st.session_state.tool = "Pen"

if "canvas_version" not in st.session_state:
    st.session_state.canvas_version = 0

# ---------------------------
# CSS for fixed toolbar
# ---------------------------
st.markdown("""
<style>
.canvas-toolbar {
    position: fixed;
    top: 120px;
    left: 20px;
    z-index: 1000;
    background-color: white;
    padding: 10px;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    width: 110px;
}

.canvas-toolbar button {
    width: 100%;
    margin-bottom: 8px;
}

/* Push canvas to the right so it doesn't go under toolbar */
.canvas-container {
    margin-left: 160px;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------
# Toolbar (FIXED)
# ---------------------------
st.markdown('<div class="canvas-toolbar">', unsafe_allow_html=True)

if st.button("✏️ Pen"):
    st.session_state.tool = "Pen"

if st.button("🧽 Eraser"):
    st.session_state.tool = "Eraser"

if st.button("🧹 Clear"):
    st.session_state.canvas_version += 1

st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------
# Tool behavior
# ---------------------------
if st.session_state.tool == "Pen":
    stroke_width = 3
    stroke_color = "#000000"
else:  # Eraser
    stroke_width = 30
    stroke_color = "#FFFFFF"

# ---------------------------
# Canvas
# ---------------------------
st.markdown('<div class="canvas-container">', unsafe_allow_html=True)

st_canvas(
    stroke_width=stroke_width,
    stroke_color=stroke_color,
    background_color="#FFFFFF",
    height=6000,
    width=1000,
    drawing_mode="freedraw",
    key=f"canvas_{st.session_state.canvas_version}",
)

st.markdown('</div>', unsafe_allow_html=True)

api_key = st.secrets["DEEPSEEK_API_KEY"]
st.write("DeepSeek key loaded:", bool(st.secrets.get("DEEPSEEK_API_KEY")))

client = OpenAI(
    api_key=st.secrets["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com"
)

TUTOR_SYSTEM_PROMPT = """
You are a calm and experienced mathematics tutor.
You assume the student is capable and intelligent.
You are not surprised by mistakes and you never rush.

When there is a small arithmetic slip, you gently invite the student to check it.
You normalize mistakes and remind the student that we are human, not machines.

When a rule is forgotten, you first ask if the student remembers it.
If they do not, you give the rule clearly and without friction.

When the approach is wrong, you guide the student back to meaning.
You speak simply, kindly, and with quiet confidence.

Your goal is not to impress, but to help the student think clearly
and succeed in exams.

All mathematical expressions, equations, symbols, functions, and operators
must be written strictly in LaTeX format.

Inline mathematics must be wrapped in $...$.
Displayed equations must be wrapped in $$...$$.

Do not write plain-text mathematics.
Do not mix natural language and symbols.
"""

st.subheader("Tutor")

for msg in st.session_state.chat:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

user_input = st.chat_input("Tell me what you're thinking or ask me something")

if user_input:
    st.session_state.chat.append({"role": "user", "content": user_input})

messages = [{"role": "system", "content": TUTOR_SYSTEM_PROMPT}]
messages += st.session_state.chat

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": TUTOR_SYSTEM_PROMPT},
        *st.session_state.chat
    ],
    temperature=0.3
)

reply = response.choices[0].message.content


st.session_state.chat.append({"role": "assistant", "content": reply})

with st.chat_message("assistant"):
        st.write(reply)

st.markdown("---")

# -----------------------------
# REINFORCEMENT AREA
# -----------------------------
st.subheader("Extra Practice (if needed)")

st.markdown(
    "- If something was difficult, we can do 2–3 more exercises together.\n"
    "- Tell me and I’ll give you similar ones.\n"
    "- If everything was clear, we move on."
)