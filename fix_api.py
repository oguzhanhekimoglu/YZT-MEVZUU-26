import re

with open('src/vlm/engine.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the payload definition
start_payload = "        payload = {"
end_payload = "        try:\n            response = requests.post("

start_pos = content.find(start_payload)
end_pos = content.find(end_payload)

new_payload = """        # Force chat API endpoint for better instruction following
        chat_url = self.api_url.replace("/api/generate", "/api/chat")
        
        payload = {
            "model":  self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [img_b64]
                }
            ],
            "stream": False,
            "options": {
                "temperature": 0.0,
                "top_p":       0.9,
                "num_predict": VLM_NUM_PREDICT,
            }
        }

"""

new_content = content[:start_pos] + new_payload + content[end_pos:]

# We also need to change the request url
new_content = new_content.replace(
    "response = requests.post(self.api_url, json=payload, timeout=VLM_TIMEOUT_S)",
    "response = requests.post(chat_url, json=payload, timeout=VLM_TIMEOUT_S)"
)

# And we need to fix the response parsing since /api/chat returns 'message': {'content': ...}
# Wait, engine.py already has a check for this!
# elif "message" in choice: raw_text = choice.get("message", {}).get("content", "").strip()
# So the response parsing is already robust!

with open('src/vlm/engine.py', 'w', encoding='utf-8') as f:
    f.write(new_content)
