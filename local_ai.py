import hashlib
import json
import urllib.parse

import requests


class LocalAI:
    def __init__(self, model="phi3:mini", personality="friendly",
                 base_url="http://localhost:11434"):
        self.model = model
        self.ollama_url = f"{base_url}/api/chat"
        self.contexts = {}
        self.personalities = {
            "friendly": "You are a warm, friendly AI assistant. Use emojis occasionally. Keep replies short (2-3 sentences).",
            "professional": "You are a professional, formal assistant. Give accurate, thorough answers. Be polite and concise.",
            "sarcastic": "You are a sarcastic AI with dry humor. Tease gently but still be helpful.",
            "poetic": "You speak in beautiful, poetic language. Use metaphors and elegant expressions.",
            "shakespeare": "Thou art a wise and eloquent AI. Speak in the style of William Shakespeare.",
        }
        self.set_personality(personality)

    def set_personality(self, name):
        self.system_prompt = self.personalities.get(name, self.personalities["friendly"])
        return f"Personality changed to: {name}"

    def get_context(self, username):
        ctx = self.contexts.setdefault(
            username, [{"role": "system", "content": self.system_prompt}])
        if ctx[0]["content"] != self.system_prompt:
            ctx[0]["content"] = self.system_prompt
        return ctx

    def post(self, messages, temperature=0.7, num_predict=200, stream=False, timeout=90):
        return requests.post(
            self.ollama_url,
            json={
                "model": self.model,
                "messages": messages,
                "stream": stream,
                "options": {"temperature": temperature, "num_predict": num_predict},
            },
            timeout=timeout,
            stream=stream,
        )

    def chat(self, username, message):
        if not message or not message.strip():
            return "Please ask me something!"
        messages = self.get_context(username)
        messages.append({"role": "user", "content": message})
        try:
            r = self.post(messages)
            if r.status_code == 200:
                reply = r.json()["message"]["content"].strip()
                messages.append({"role": "assistant", "content": reply})
                if len(messages) > 31:
                    self.contexts[username] = [messages[0]] + messages[-30:]
                return reply
            return f"Ollama error: {r.status_code}"
        except requests.exceptions.ConnectionError:
            return "Error: Ollama not running. Please run 'ollama serve'"
        except Exception as e:
            return f"Error: {e}"

    def chat_with_history(self, username, system_context, turns):
        messages = [{"role": "system", "content": self.system_prompt}]
        if system_context:
            messages.append({"role": "system", "content": system_context})
        messages.extend(turns)
        try:
            r = self.post(messages, temperature=0.6, num_predict=250)
            if r.status_code == 200:
                return r.json()["message"]["content"].strip()
            return f"Ollama error: {r.status_code}"
        except requests.exceptions.ConnectionError:
            return "Error: Ollama not running."
        except Exception as e:
            return f"Error: {e}"

    def chat_stream(self, username, message):
        messages = self.get_context(username)
        messages.append({"role": "user", "content": message})
        try:
            r = self.post(messages, stream=True, timeout=120)
            if r.status_code != 200:
                yield f"Ollama error: {r.status_code}"
                return
            full = []
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                delta = chunk.get("message", {}).get("content", "")
                if delta:
                    full.append(delta)
                    yield delta
                if chunk.get("done"):
                    break
            messages.append({"role": "assistant", "content": "".join(full)})
            if len(messages) > 31:
                self.contexts[username] = [messages[0]] + messages[-30:]
        except Exception as e:
            yield f"Error: {e}"

    def generate_image(self, prompt):
        encoded = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded}"
        headers = {"User-Agent": "Mozilla/5.0 (chat-system)"}
        try:
            r = requests.get(url, headers=headers, timeout=90, allow_redirects=True)
            ctype = r.headers.get("content-type", "")
            if r.status_code == 200 and "image" in ctype:
                data = r.content
                fname = f"generated_{hashlib.md5(prompt.encode()).hexdigest()[:8]}.png"
                with open(fname, "wb") as f:
                    f.write(data)
                return {"success": True, "data": data, "filename": fname}
            return {"success": False, "error": f"API returned {ctype or 'non-image'}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def summarize_chat(self, messages_text):
        prompt = ("Summarize this conversation between multiple users in 2-3 short "
                  "sentences. Capture main topics and key points:\n\n"
                  f"{messages_text}\n\nSummary:")
        try:
            r = self.post([{"role": "user", "content": prompt}],
                          temperature=0.3, num_predict=120)
            if r.status_code == 200:
                return r.json()["message"]["content"].strip()
            return "Could not generate summary."
        except Exception as e:
            return f"Summary error: {e}"

    def extract_keywords(self, messages_text):
        prompt = ("Extract the 5 most important keywords from this conversation. "
                  "Return only the keywords separated by commas:\n\n"
                  f"{messages_text}\n\nKeywords:")
        try:
            r = self.post([{"role": "user", "content": prompt}],
                          temperature=0, num_predict=50)
            if r.status_code == 200:
                return r.json()["message"]["content"].strip()
            return "Could not extract keywords."
        except Exception as e:
            return f"Keyword error: {e}"

    def analyze_sentiment(self, message):
        prompt = ("Analyze the sentiment of this message and return ONLY one word "
                  "(Positive, Neutral, or Negative):\n"
                  f'Message: "{message}"\nSentiment:')
        try:
            r = self.post([{"role": "user", "content": prompt}],
                          temperature=0, num_predict=10, timeout=30)
            if r.status_code == 200:
                s = r.json()["message"]["content"].strip().lower()
                if "positive" in s:
                    return "positive", "😊"
                if "negative" in s:
                    return "negative", "😞"
                return "neutral", "😐"
        except Exception:
            pass
        return "neutral", "😐"