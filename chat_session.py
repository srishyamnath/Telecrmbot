class ChatSession:
    def __init__(self):
        self.history = []
        self.temp_lead_data = {} # NEW: Dictionary to store temporary lead data

    def add_user_message(self, message):
        self.history.append({"role": "user", "content": message})

    def add_bot_message(self, message):
        self.history.append({"role": "bot", "content": message})

    def reset(self):
        self.history = []
        self.temp_lead_data = {} # NEW: Reset temp data too

    def get_history(self):
        return self.history

    def format_for_prompt(self):
        return "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in self.history])

    # NEW: Methods to manage temporary lead data
    def set_temp_lead_data(self, key, value):
        self.temp_lead_data[key] = value

    def get_temp_lead_data(self, key=None):
        if key:
            return self.temp_lead_data.get(key)
        return self.temp_lead_data