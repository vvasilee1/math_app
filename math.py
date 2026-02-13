import streamlit as st
from streamlit_drawable_canvas import st_canvas
from openai import OpenAI
from PIL import Image
import numpy as np
import io
import base64
import requests
import hashlib

ACCESS_CODE = "1a2b3c!8"

code = st.text_input("Enter access code", type="password")

if code != ACCESS_CODE:
    st.stop()



st.set_page_config(layout="wide")

st.markdown("""
<style>
#floating-toolbar {
    position: fixed;
    top: 90px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 10000;
    background: white;
    padding: 10px 16px;
    border-radius: 10px;
    box-shadow: 0 6px 18px rgba(0,0,0,0.2);
}
</style>
""", unsafe_allow_html=True)

if "tool" not in st.session_state:
    st.session_state.tool = "pen"

if "canvas_version" not in st.session_state:
    st.session_state.canvas_version = 0

st.markdown(
    """
    <style>
        section[data-testid="stSidebar"] {
            width: 50px !important; # Set your desired width here
        }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    if st.button("✏️ Pen"):
        st.session_state.tool = "pen"
    if st.button("🧽 Eraser"):
        st.session_state.tool = "eraser"
    if st.button("🗑️ Clear"):
        st.session_state.canvas_version += 1


st.markdown("<br><br><br><br><br>", unsafe_allow_html=True)



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

When the student explicitly asks for methodology,
you explain the general strategy before solving.
You guide step-by-step and invite participation.
You avoid giving the full final answer immediately.


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

stroke_width = 3 if st.session_state.tool == "pen" else 20

canvas_result=st_canvas(
    stroke_width=stroke_width,
    stroke_color="#000000",
    background_color="#FFFFFF",
    height=10000,
    width=1300,
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

def ai_call(system_prompt: str, user_content: str, max_tokens=500,temperature: float = 0.2) -> str:
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        temperature=temperature,
        max_tokens=max_tokens
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
        with st.spinner("Thinking carefully..."):
            tutor_feedback = ai_call(
            TUTOR_SYSTEM_PROMPT,
            tutor_user_prompt,
            max_tokens=500,
            temperature=0.3
        )

        # 🔑 Persist it
        st.session_state.tutor_feedback = tutor_feedback
        st.session_state.last_latex = latex

if st.button("Teach me how to solve this"):

    latex = image_to_latex(canvas_result.image_data)

    if not latex:
        st.warning("I couldn't read the exercise clearly yet.")
    else:
        methodology_prompt = f"""
The student wrote the following mathematical exercise:

{latex}

The student does not know how to solve it.

Please:
- Identify what type of problem this is.
- Explain the general method clearly.
- Break the solution into structured steps.
- Do NOT immediately give the final answer.
- Encourage the student to try Step 1 first.
"""
        with st.spinner("Thinking carefully..."):
            methodology_response = ai_call(
            TUTOR_SYSTEM_PROMPT,
            methodology_prompt,
            max_tokens=500,
            temperature=0.3
        )

        st.session_state.methodology = methodology_response
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

if "methodology" in st.session_state:
    st.markdown("### How to approach this problem")
    st.write(st.session_state.methodology)

if "last_latex" in st.session_state:
    st.latex(st.session_state.last_latex)






