import streamlit as st
from streamlit_drawable_canvas import st_canvas
from openai import OpenAI
from PIL import Image
import numpy as np
import io
import base64
import requests


ACCESS_CODE = "1a2b3c!8"

code = st.text_input("Enter access code", type="password")

if code != ACCESS_CODE:
    st.stop()


if "canvas_version" not in st.session_state:
    st.session_state.canvas_version = 0

if "tool" not in st.session_state:
    st.session_state.tool = "Pen"



if "canvas_key" not in st.session_state:
    st.session_state.canvas_key = 0



with st.container():
    st.markdown('<div class="canvas-toolbar">', unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("✏️ Pen"):
        st.session_state.tool = "Pen"

with col2:
    if st.button("🧽 Eraser"):
        st.session_state.tool = "Eraser"

with col3:
    if st.button("🧹 Clear All"):
        st.session_state.canvas_version += 1



# CONFIG
# -----------------------------
api_key = st.secrets["DEEPSEEK_API_KEY"]
st.write("DeepSeek key loaded:", bool(st.secrets.get("DEEPSEEK_API_KEY")))

client = OpenAI(
    api_key=st.secrets["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com"
)

layers = [
    "Layer 1: Fractions, Decimals, Powers",
    "Layer 2: Identities, Factorization",
    "Layer 3: Functions",
    "Layer 4: Graphs of functions",
    "Layer 5: Logarithms, Exponents, Sequences",
    "Layer 6: Trigonometric functions & properties",
    "Layer 7: Complex numbers",
    "Layer 8: Continuity, Functional Equations",
    "Layer 9: Derivatives, Integrals"
]

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

Even when explaining use only math expressions no latex code

Rules:
- Use short math-style phrases.
- Prefer parentheses and linear notation.




"""

# -----------------------------
# STATE INIT
# -----------------------------


if "chat" not in st.session_state:
    st.session_state.chat = []

# -----------------------------
# UI
# -----------------------------
layer = st.selectbox("Choose Layer", layers)
st.header(layer)

st.markdown(
    "Write your own exercises on the canvas and solve them.\n"
    "If something feels wrong or confusing, talk to me below."
)

# -----------------------------
# TOOLS
# -----------------------------
tool = st.radio("Tool", ["Pen", "Eraser"], horizontal=True)
if st.session_state.tool == "Pen":
    stroke_width = 3
    stroke_color = "#000000"
else:  # Eraser
    stroke_width = 10
    stroke_color = "#FFFFFF"

canvas_key = f"{layer}_{st.session_state.canvas_version}"

canvas_result=st_canvas(
    stroke_width=stroke_width,
    stroke_color=stroke_color,
    background_color="#FFFFFF",
    height=6000,
    width=1000,
    drawing_mode="freedraw",
    key=f"canvas_{st.session_state.canvas_version}",
)

def clean_latex(latex: str) -> str:
    replacements = {
        r"\left": "",
        r"\right": "",
        r"\,": "",
    }
    for k, v in replacements.items():
        latex = latex.replace(k, v)
    return latex.strip()

def ai_call(system_prompt: str, user_content: str, temperature: float = 0.2) -> str:
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        temperature=temperature
    )
    return response.choices[0].message.content.strip()

def image_to_latex(image_data: np.ndarray) -> str:
    """
    Convert canvas image data to LaTeX using Mathpix.
    Returns an empty string if conversion fails.
    """

    if image_data is None:
        return ""

    # 1. Convert numpy array to PNG
    image = Image.fromarray(image_data.astype("uint8"))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    img_base64 = base64.b64encode(buffer.getvalue()).decode()

    # 2. Call Mathpix
    response = requests.post(
        "https://api.mathpix.com/v3/text",
        headers={
            "app_id": st.secrets["MATHPIX_APP_ID"],
            "app_key": st.secrets["MATHPIX_APP_KEY"],
            "Content-type": "application/json"
        },
        json={
            "src": f"data:image/png;base64,{img_base64}",
            "formats": ["latex_styled"]
        }
    )

    if response.status_code != 200:
        return ""

    latex = response.json().get("latex_styled", "")

    return clean_latex(latex)

if st.button("Check my work"):

    latex = image_to_latex(canvas_result.image_data)

    if latex:
        tutor_user_prompt = f"""
Here is the student's handwritten mathematics, converted to LaTeX:

{latex}

Please:
- Check whether the reasoning is correct.
- If there is a small mistake, gently invite the student to check it.
- If a rule is forgotten, ask first, then give it clearly.
"""

        tutor_feedback = ai_call(
            TUTOR_SYSTEM_PROMPT,
            tutor_user_prompt,
            temperature=0.3
        )

        # 🔑 Persist it
        st.session_state.tutor_feedback = tutor_feedback
        st.session_state.last_latex = latex

    
st.markdown("---")
# -----------------------------
# TUTOR CONVERSATION
# -----------------------------
st.subheader("Tutor")

for msg in st.session_state.chat:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

user_input = st.chat_input("Tell me what you're thinking or ask me something")

if user_input:
    st.session_state.chat.append({"role": "user", "content": user_input})

messages = [{"role": "system", "content": TUTOR_SYSTEM_PROMPT}]
messages += st.session_state.chat


if "tutor_feedback" in st.session_state:
    st.markdown("### Tutor’s note")
    st.write(st.session_state.tutor_feedback)

if "last_latex" in st.session_state:
    st.latex(st.session_state.last_latex)


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
