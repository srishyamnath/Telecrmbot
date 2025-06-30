# gemini_bot.py
import os
import google.generativeai as genai

# ✅ Setup API key securely (change for your environment if needed)
GOOGLE_API_KEY = os.getenv("GEMINI_API_KEY") or "YOUR_FALLBACK_API_KEY_IF_ENV_NOT_SET" # Use a fallback if .env not loaded for testing
genai.configure(api_key=GOOGLE_API_KEY)

# ✅ Load Gemini model
model = genai.GenerativeModel("gemini-1.5-flash")

# ✅ Function to generate response with memory
def get_response(user_input: str, history: list) -> str:
    # Format history into a prompt string
    formatted_history = ""
    for msg in history:
        role = msg['role'].capitalize()
        content = msg['content']
        formatted_history += f"{role}: {content}\n"

    # Add current question
    prompt = f"{formatted_history}User: {user_input}\nBot:"

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"⚠️ Gemini Error: {e}"