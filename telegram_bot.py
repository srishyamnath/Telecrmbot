# telegram_bot.py
import os
import asyncio
from telegram import Update, ForceReply, ReplyKeyboardRemove, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters,
    ConversationHandler
)
from chat_session import ChatSession
from gemini_bot import get_response as gemini_respond
from ollama_bot import get_response as ollama_respond
from zoho_leads import search_lead_by_phone, create_lead
from zoho_auth import get_access_token
from config import TELEGRAM_BOT_TOKEN
import logging

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# === Per-user session memory ===
user_sessions = {}       # user_id -> ChatSession
user_models = {}         # user_id -> 'gemini' or 'ollama'

# Conversation states for lead capture
GET_NAME, GET_EMAIL, CONFIRM_PHONE = range(3)

# === Start Command ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Ensure a session exists
    session = user_sessions.setdefault(user_id, ChatSession())
    session.reset() # Clear previous session data if starting new
    user_models.setdefault(user_id, "gemini") # default model

    phone_number = update.message.contact.phone_number if update.message.contact else None

    logger.info(f"User {user_id} started conversation. Phone: {phone_number}")

    reply_keyboard = [[KeyboardButton(text="Share My Contact", request_contact=True)]]
    markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)


    if phone_number:
        phone_number = phone_number.replace(" ", "").strip()
        if not phone_number.startswith('+'):
            # Basic attempt to add +91 for Indian numbers if missing, you can refine this
            if len(phone_number) == 10 and phone_number.isdigit():
                phone_number = '+91' + phone_number
            else:
                await update.message.reply_text(
                    "Please provide a valid phone number with country code (e.g., +919876543210).",
                    reply_markup=markup
                )
                session.set_temp_lead_data('current_state', GET_NAME) # Go to name if phone invalid
                return GET_NAME # Go to GET_NAME state to collect details

        session.set_temp_lead_data('phone_number', phone_number)

        lead = search_lead_by_phone(phone_number)
        if lead:
            first_name = lead.get('First_Name', 'there')
            last_name = lead.get('Last_Name', '')
            full_name = f"{first_name} {last_name}".strip()
            # Personalized greeting using LLM
            prompt = f"The user's name is {full_name}. Greet them warmly and offer assistance based on typical SaaS product inquiries. Keep it concise and professional. Mention that you're an Indian Law Bot."

            # Use the selected LLM
            respond = gemini_respond if user_models[user_id] == "gemini" else ollama_respond
            llm_greeting = respond(prompt, history=session.get_history()) # Pass current session history for context

            await update.message.reply_text(f"👋 {llm_greeting}", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END # End conversation for existing lead
        else:
            await update.message.reply_text(
                "Welcome to Indian Law Bot! It seems you're new here. To help us personalize your experience and answer your legal queries accurately, could you please tell me your first name?"
            )
            session.set_temp_lead_data('current_state', GET_NAME)
            return GET_NAME
    else:
        await update.message.reply_text(
            "Welcome to Indian Law Bot! To get started, you can either share your contact number using the 'Share Contact' button below, or type your first name so we can assist you better.",
            reply_markup=markup
        )
        session.set_temp_lead_data('current_state', GET_NAME)
        return GET_NAME

# === Lead Capture Handlers ===
async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    session = user_sessions.setdefault(user_id, ChatSession()) # Ensure session exists

    # Only proceed if the state is correct, or if user sends initial text and no phone was shared
    current_state = session.get_temp_lead_data('current_state')
    if current_state != GET_NAME and not (not session.get_temp_lead_data('phone_number') and not update.message.contact):
        await update.message.reply_text("Please start over by sending a message or your contact, or continue the current flow.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END # Or return the current state if you want to be stricter

    user_name = update.message.text
    if not user_name or len(user_name) < 2:
        await update.message.reply_text("Please provide a valid name.")
        return GET_NAME # Stay in GET_NAME state

    session.set_temp_lead_data('first_name', user_name)
    logger.info(f"User {user_id} provided name: {user_name}")

    await update.message.reply_text("Great! Now, could you please provide your email address?")
    session.set_temp_lead_data('current_state', GET_EMAIL)
    return GET_EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    session = user_sessions.setdefault(user_id, ChatSession())

    if session.get_temp_lead_data('current_state') != GET_EMAIL:
        await update.message.reply_text("Please start over by sending a message or your contact, or continue the current flow.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    user_email = update.message.text
    # Basic email validation
    if "@" not in user_email or "." not in user_email or len(user_email) < 5:
        await update.message.reply_text("That doesn't look like a valid email. Please try again.")
        return GET_EMAIL

    session.set_temp_lead_data('email', user_email)
    logger.info(f"User {user_id} provided email: {user_email}")

    # If phone number wasn't shared initially, ask for it
    if not session.get_temp_lead_data('phone_number'):
        await update.message.reply_text(
            "Almost there! Finally, please confirm your phone number (including country code, e.g., +919876543210)."
        )
        session.set_temp_lead_data('current_state', CONFIRM_PHONE)
        return CONFIRM_PHONE
    else:
        return await finalize_lead_creation(update, context)

async def confirm_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    session = user_sessions.setdefault(user_id, ChatSession())

    if session.get_temp_lead_data('current_state') != CONFIRM_PHONE:
        await update.message.reply_text("Please start over by sending a message or your contact, or continue the current flow.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    phone_number = update.message.text
    # Basic phone number validation
    if not phone_number.startswith('+') or not phone_number[1:].isdigit() or len(phone_number) < 10:
        await update.message.reply_text("Please provide a valid phone number with country code (e.g., +919876543210).")
        return CONFIRM_PHONE

    session.set_temp_lead_data('phone_number', phone_number)
    logger.info(f"User {user_id} confirmed phone: {phone_number}")

    return await finalize_lead_creation(update, context)

async def finalize_lead_creation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    session = user_sessions.setdefault(user_id, ChatSession())
    user_data = session.get_temp_lead_data()

    first_name = user_data.get('first_name')
    email = user_data.get('email')
    phone_number = user_data.get('phone_number')

    if not all([first_name, email, phone_number]):
        await update.message.reply_text("Something went wrong with collecting your details. Please try again or type /reset to start over.", reply_markup=ReplyKeyboardRemove())
        session.reset()
        return ConversationHandler.END

    logger.info(f"Attempting to create lead for {first_name}, {email}, {phone_number}")

    # Zoho CRM API call to create lead
    new_lead = create_lead(first_name, "User", email, phone_number) # "User" as default last name for last_name

    # Use the selected LLM for confirmation
    respond = gemini_respond if user_models[user_id] == "gemini" else ollama_respond

    if new_lead:
        prompt = f"A new lead named {first_name} with email {email} and phone {phone_number} has been created in CRM. Thank them for their details and assure them that someone from Indian Law Bot will reach out soon. Offer to answer a legal question now. Be concise."
        llm_confirmation = respond(prompt, history=session.get_history())
        await update.message.reply_text(f"✅ {llm_confirmation}", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text(
            "Thank you for your details! However, I had some trouble saving them to our CRM. Please try again later or contact us directly. In the meantime, I can still answer your legal questions.",
            reply_markup=ReplyKeyboardRemove()
        )

    session.reset() # Clear session data after lead creation
    return ConversationHandler.END

# === Model Selection ===
async def model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = user_sessions.setdefault(user_id, ChatSession()) # Ensure session exists

    if len(context.args) == 0:
        await update.message.reply_text("Please specify a model: /model gemini or /model ollama")
        return
    choice = context.args[0].lower()
    if choice in ["gemini", "ollama"]:
        user_models[user_id] = choice
        await update.message.reply_text(f"✅ Model set to: {choice.capitalize()}")
        # Also reset conversation state if mid-lead capture
        if session.get_temp_lead_data('current_state'):
            session.reset()
            await update.message.reply_text("Lead capture flow reset due to model change. Please start again if you wish to provide details.", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
    else:
        await update.message.reply_text("❌ Invalid model. Use /model gemini or /model ollama")

# === Reset Command ===
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    session = user_sessions.setdefault(user_id, ChatSession())
    session.reset() # Resets both history and temp_lead_data
    await update.message.reply_text("🧠 Memory and lead capture context reset. Start a new legal query.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END # End any ongoing conversation

# === Handle User Messages (Modified for general chat after lead capture or for existing leads) ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    query = update.message.text

    # If the user is in a lead capture state, this handler shouldn't activate (ConversationHandler handles it)
    # This `handle_message` function will primarily respond to general queries after lead capture is done,
    # or for users who are already in CRM.

    session = user_sessions.setdefault(user_id, ChatSession())
    model_choice = user_models.setdefault(user_id, "gemini")

    # Add user input to memory
    session.add_user_message(query)

    # Limit history to last 4 turns for LLM (adjust as needed)
    short_history = session.get_history()[-4:]

    # Generate response
    respond = gemini_respond if model_choice == "gemini" else ollama_respond
    response = respond(query, short_history)

    # Add bot reply to memory
    session.add_bot_message(response)

    await update.message.reply_text(f"🤖 {response}")

# === Fallback Handler ===
async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles messages when the bot is in an unexpected state or doesn't understand."""
    user_id = update.effective_user.id
    session = user_sessions.setdefault(user_id, ChatSession())
    current_state = session.get_temp_lead_data('current_state')
    logger.warning(f"Fallback triggered for user {user_id}. Current state: {current_state}. Message: {update.message.text}")

    if current_state: # If there's an ongoing conversation, guide them back
        if current_state == GET_NAME:
            await update.message.reply_text("I'm expecting your first name. Please type it now.")
        elif current_state == GET_EMAIL:
            await update.message.reply_text("I'm expecting your email address. Please type it now.")
        elif current_state == CONFIRM_PHONE:
            await update.message.reply_text("I'm expecting your phone number with country code. Please type it now.")
        return current_state # Stay in the current state
    else: # No active conversation state related to lead capture
        # Fallback to general chat handling if not in a specific lead capture state
        return await handle_message(update, context) # Route to general message handler


# === Run Bot ===
def main() -> None:
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Conversation handler for lead capture flow
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start), # Can start with /start
            MessageHandler(filters.TEXT & ~filters.COMMAND, start), # Can start by just typing
            MessageHandler(filters.CONTACT, start) # Can start by sharing contact
        ],
        states={
            GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            GET_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
            CONFIRM_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_phone)],
        },
        fallbacks=[
            CommandHandler("cancel", reset), # Use reset as cancel
            CommandHandler("reset", reset),
            MessageHandler(filters.TEXT & ~filters.COMMAND, fallback) # General text fallback for unknown states
        ],
    )

    application.add_handler(conv_handler)
    # Add other handlers outside of the conversation if they should always work
    application.add_handler(CommandHandler("model", model))
    # `handle_message` should ideally be the final catch-all *after* conversation handlers.
    # If a message doesn't match any conversation state, it will fall through to here.
    # However, since `fallback` above already routes unhandled texts to `handle_message`
    # if not in a lead capture state, explicitly adding it here might be redundant or
    # cause issues if not carefully ordered. For now, rely on `fallback`.


    logger.info("🤖 Telegram bot is running...")
    logger.info("Ensure Zoho Access Token is generated by running zoho_auth.py once.")
    # Check if Zoho token exists (simple check, ideally load from persistent store)
    if not get_access_token():
        logger.warning("Zoho access token is not yet generated or loaded. Run zoho_auth.py manually once.")


    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()