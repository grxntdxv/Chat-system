import io
import select
import threading
import tkinter as tk
from tkinter import scrolledtext

from PIL import Image, ImageTk

import chat_protocol as proto
from chat_utils import S_LOGGEDIN, S_OFFLINE, menu

SKIP_SENTIMENT_PREFIXES = (
    "++++ Choose", "Time", "Users:", "Rooms:", "Sonnet", "See you",
    "You are disconnected", "Connected to", "Requesting to add",
    "How did you", "Chat ended", "joined the chat", "Quitting",
)


class GUI:
    def __init__(self, send_func, recv_func, state_machine, sock, ai_bot=None):
        self.ai_bot = ai_bot
        self.send = send_func
        self.recv = recv_func
        self.sm = state_machine
        self.socket = sock
        self.my_msg = ""
        self.running = True
        self.after_id = None
        self.username = ""
        self.image_cache = []
        self.generating_image = False
        self.sentiment_enabled = True
        self.chat_log = []
        self.max_chat_log = 300

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def show_login(self):
        self.login_win = tk.Toplevel()
        self.login_win.title("Login")
        self.login_win.attributes("-fullscreen", True)
        self.login_win.bind("<Escape>",
                            lambda e: self.login_win.attributes("-fullscreen", False))
        self.login_win.configure(bg="#350616")

        sh = self.login_win.winfo_screenheight()
        tk.Label(self.login_win, text="Please login to continue",
                 font=("Helvetica", int(sh * 0.04), "bold"),
                 bg="#350616", fg="#EAECEE").place(relx=0.5, rely=0.12, anchor="center")

        tk.Label(self.login_win, text="Name:", font=("Helvetica", int(sh * 0.025)),
                 bg="#350616", fg="#EAECEE").place(relx=0.5, rely=0.28, anchor="center")
        self.name_entry = tk.Entry(self.login_win, font=("Helvetica", int(sh * 0.025)),
                                   width=25, bg="#4A1C2A", fg="#EAECEE",
                                   insertbackground="#EAECEE")
        self.name_entry.place(relx=0.5, rely=0.35, anchor="center")

        tk.Label(self.login_win, text="Password:", font=("Helvetica", int(sh * 0.025)),
                 bg="#350616", fg="#EAECEE").place(relx=0.5, rely=0.45, anchor="center")
        self.pass_entry = tk.Entry(self.login_win, font=("Helvetica", int(sh * 0.025)),
                                   show="*", width=25, bg="#4A1C2A", fg="#EAECEE",
                                   insertbackground="#EAECEE")
        self.pass_entry.place(relx=0.5, rely=0.52, anchor="center")
        self.name_entry.focus()

        tk.Button(self.login_win, text="FORGOT PASSWORD",
                  font=("Helvetica", int(sh * 0.015)),
                  bg="#350616", fg="#EAECEE", activebackground="#4A1C2A",
                  command=self.show_forgot_password).place(relx=0.5, rely=0.62,
                                                          anchor="center")
        tk.Button(self.login_win, text="LOGIN",
                  font=("Helvetica", int(sh * 0.02), "bold"), width=15,
                  bg="#350616", fg="#EAECEE", activebackground="#4A1C2A",
                  command=self.do_login).place(relx=0.5, rely=0.70, anchor="center")
        tk.Button(self.login_win, text="REGISTER NEW USER",
                  font=("Helvetica", int(sh * 0.02), "bold"), width=20,
                  bg="#350616", fg="#EAECEE", activebackground="#4A1C2A",
                  command=self.show_register).place(relx=0.5, rely=0.80, anchor="center")

        self.error_label = tk.Label(self.login_win, text="", fg="red",
                                    font=("Helvetica", int(sh * 0.02)), bg="#350616")
        self.error_label.place(relx=0.5, rely=0.88, anchor="center")
        self.root.mainloop()

    def do_login(self):
        name = self.name_entry.get().strip()
        pw = self.pass_entry.get().strip()
        if not name or not pw:
            self.error_label.config(text="name and password required")
            return
        if not self.send(proto.make("login", name=name, password=pw)):
            self.error_label.config(text="could not send login")
            return
        r = proto.parse(self.recv())
        if not r:
            self.error_label.config(text="server unreachable")
            return
        st = r.get("status")
        if st == "ok":
            self.sm.set_state(S_LOGGEDIN)
            self.sm.set_myname(name)
            self.username = name
            self.login_win.destroy()
            self.build_main_window(name)
            self.after_id = self.root.after(100, self.poll_messages)
        elif st == "invalid":
            self.error_label.config(text="invalid username or password")
        elif st == "duplicate":
            self.error_label.config(text="user already logged in")
        else:
            self.error_label.config(text="login failed: " + str(st))

    def show_register(self):
        w = tk.Toplevel(self.login_win)
        w.title("Register")
        w.geometry("420x560")
        w.configure(bg="#350616")

        def lbl(t, f=12, b=False):
            return tk.Label(w, text=t, font=("Helvetica", f, "bold" if b else "normal"),
                            bg="#350616", fg="#EAECEE")

        def ent(show=None):
            return tk.Entry(w, font=("Helvetica", 13), width=25, show=show,
                            bg="#4A1C2A", fg="#EAECEE", insertbackground="#EAECEE")

        lbl("Create New Account", 16, True).pack(pady=15)
        lbl("Username:").pack(); name_e = ent(); name_e.pack(pady=4)
        lbl("Password:").pack(); pw_e = ent(show="*"); pw_e.pack(pady=4)
        lbl("Confirm:").pack(); cf_e = ent(show="*"); cf_e.pack(pady=4)
        lbl("Security question:").pack(); q_e = ent(); q_e.pack(pady=4)
        q_e.insert(0, "What is your favorite color?")
        lbl("Answer:").pack(); a_e = ent(); a_e.pack(pady=4)
        err = tk.Label(w, text="", fg="red", bg="#350616"); err.pack(pady=8)

        def do():
            n, p, c, q, a = (name_e.get().strip(), pw_e.get().strip(),
                             cf_e.get().strip(), q_e.get().strip(),
                             a_e.get().strip().lower())
            if not n or not p or p != c or not a:
                err.config(text="all fields required, passwords must match")
                return
            self.send(proto.make("register", name=n, password=p,
                                 security_q=q, security_a=a))
            r = proto.parse(self.recv())
            if r and r.get("status") == "ok":
                err.config(text="registered, you can now login", fg="green")
                w.after(1500, w.destroy)
            elif r and r.get("status") == "exists":
                err.config(text="username taken", fg="red")
            else:
                err.config(text="registration failed", fg="red")

        tk.Button(w, text="REGISTER", font=("Helvetica", 12, "bold"),
                  bg="#350616", fg="#EAECEE", command=do).pack(pady=15)
        tk.Button(w, text="CANCEL", bg="#350616", fg="#EAECEE",
                  command=w.destroy).pack()

    def show_forgot_password(self):
        w = tk.Toplevel(self.login_win)
        w.title("Reset Password")
        w.geometry("420x520")
        w.configure(bg="#350616")
        tk.Label(w, text="Reset Password", font=("Helvetica", 16, "bold"),
                 bg="#350616", fg="#EAECEE").pack(pady=15)
        tk.Label(w, text="Username:", bg="#350616", fg="#EAECEE").pack()
        name_e = tk.Entry(w, font=("Helvetica", 13), width=25, bg="#4A1C2A",
                          fg="#EAECEE", insertbackground="#EAECEE")
        name_e.pack(pady=5)
        q_lbl = tk.Label(w, text="", wraplength=380, bg="#350616", fg="#EAECEE",
                         font=("Helvetica", 11, "italic"))
        q_lbl.pack(pady=8)
        tk.Label(w, text="Answer:", bg="#350616", fg="#EAECEE").pack()
        ans_e = tk.Entry(w, font=("Helvetica", 13), width=25, bg="#4A1C2A",
                         fg="#EAECEE", insertbackground="#EAECEE")
        ans_e.pack(pady=5)
        tk.Label(w, text="New Password:", bg="#350616", fg="#EAECEE").pack()
        np_e = tk.Entry(w, font=("Helvetica", 13), width=25, show="*",
                        bg="#4A1C2A", fg="#EAECEE", insertbackground="#EAECEE")
        np_e.pack(pady=5)
        err = tk.Label(w, text="", bg="#350616", fg="red"); err.pack(pady=8)
        state = {"name": None}

        def get_q():
            n = name_e.get().strip()
            if not n:
                err.config(text="enter username", fg="red"); return
            self.send(proto.make("reset_request", name=n))
            r = proto.parse(self.recv())
            if r and r.get("status") == "ok":
                q_lbl.config(text=f"Q: {r.get('question','')}")
                state["name"] = n
                err.config(text="answer to reset", fg="green")
            else:
                err.config(text="user not found", fg="red")

        def reset():
            n = state["name"]
            if not n:
                err.config(text="verify username first", fg="red"); return
            a, new = ans_e.get().strip().lower(), np_e.get().strip()
            if not a or len(new) < 4:
                err.config(text="answer and password (>=4 chars) required", fg="red")
                return
            self.send(proto.make("reset_confirm", name=n, answer=a,
                                 new_password=new))
            r = proto.parse(self.recv())
            if r and r.get("status") == "ok":
                err.config(text="password reset", fg="green")
                w.after(1500, w.destroy)
            else:
                err.config(text="wrong answer", fg="red")

        tk.Button(w, text="GET QUESTION", bg="#350616", fg="#EAECEE",
                  command=get_q).pack(pady=6)
        tk.Button(w, text="RESET", bg="#350616", fg="#EAECEE",
                  font=("Helvetica", 12, "bold"),
                  command=reset).pack(pady=10)

    def build_main_window(self, name):
        self.root.deiconify()
        self.root.title(f"ChatRoom - {name}")
        self.root.geometry("900x650")
        self.root.configure(bg="#350616")

        tk.Label(self.root, text=name, bg="#350616", fg="#EAECEE",
                 font=("Helvetica", 15, "bold"), pady=5).pack(fill=tk.X)

        self.chat_area = scrolledtext.ScrolledText(
            self.root, wrap=tk.WORD, bg="#1a0308", fg="#EAECEE",
            font=("Helvetica", 13), state=tk.DISABLED)
        self.chat_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        bar = tk.Frame(self.root, bg="#350616"); bar.pack(fill=tk.X, side=tk.BOTTOM)
        self.entry_msg = tk.Entry(bar, bg="#4A1C2A", fg="#EAECEE",
                                  font=("Helvetica", 13),
                                  insertbackground="#EAECEE")
        self.entry_msg.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.entry_msg.focus()
        self.entry_msg.bind("<Return>", lambda e: self.send_callback())

        def btn(t, cmd, pad=4):
            tk.Button(bar, text=t, bg="#350616", fg="#EAECEE",
                      font=("Helvetica", 10, "bold"), command=cmd
                      ).pack(side=tk.RIGHT, padx=pad, pady=5)

        btn("Send", self.send_callback)
        btn("Connect", self.show_connect_dialog)
        btn("Summary", self.show_summary)
        btn("Keywords", self.show_keywords)
        btn("Rooms", self.show_rooms)
        btn("Sentiment", self.toggle_sentiment)
        btn("Quit", lambda: self.send_command("q"))

        self.display_message(menu)

    def send_callback(self):
        msg = self.entry_msg.get().strip()
        if not msg:
            return
        self.entry_msg.delete(0, tk.END)
        self.my_msg = ""

        if msg.startswith("/aipic:"):
            self.handle_aipic(msg)
            return
        if msg.startswith("@ai ") or msg.startswith("/ai "):
            self.handle_ai(msg[4:].strip())
            return
        if msg.startswith("/summary"):
            self.show_summary(); return
        if msg.startswith("/keywords"):
            self.show_keywords(); return
        if msg.startswith("/rooms"):
            self.show_rooms(); return
        if msg.startswith("/history"):
            parts = msg.split()
            n = parts[1] if len(parts) > 1 and parts[1].isdigit() else "30"
            self.my_msg = f"/history {n}"
            return

        self.my_msg = msg

    def send_command(self, cmd):
        self.my_msg = cmd

    def handle_aipic(self, msg):
        if self.generating_image:
            self.display_message("[Image] still generating")
            return
        prompt = msg[7:].strip()
        if not prompt:
            self.display_message("[Image] usage: /aipic: <description>")
            return
        if self.ai_bot is None:
            self.display_message("[Image] AI not available")
            return
        self.display_message(f"[Image] generating: {prompt}")
        self.generating_image = True

        def work():
            try:
                result = self.ai_bot.generate_image(prompt)
            finally:
                self.root.after(0, lambda: setattr(self, "generating_image", False))
            self.root.after(0, lambda: self.handle_image_result(result))
        threading.Thread(target=work, daemon=True).start()

    def handle_ai(self, question):
        if not question:
            self.display_message("[AI] usage: @ai <question>")
            return
        if self.ai_bot is None:
            self.display_message("[AI] AI not available")
            return
        self.display_message("[AI] thinking...")

        def work():
            try:
                reply = self.ai_bot.chat(self.username, question)
            except Exception as e:
                reply = f"error: {e}"
            self.root.after(0, lambda: self.display_message(f"[AI] {reply}"))
        threading.Thread(target=work, daemon=True).start()

    def handle_image_result(self, result):
        if result.get("success"):
            self.display_image(result["data"], result["filename"])
        else:
            self.display_message(f"[Image] error: {result.get('error')}")

    def show_connect_dialog(self):
        d = tk.Toplevel(self.root); d.title("Connect"); d.geometry("260x130")
        d.configure(bg="#350616")
        tk.Label(d, text="Username:", bg="#350616", fg="#EAECEE").pack(pady=8)
        e = tk.Entry(d, bg="#4A1C2A", fg="#EAECEE", insertbackground="#EAECEE")
        e.pack(); e.focus()

        def go():
            u = e.get().strip()
            if u:
                d.destroy()
                self.send_command(f"c {u}")
        tk.Button(d, text="Connect", bg="#350616", fg="#EAECEE",
                  command=go).pack(pady=10)
        e.bind("<Return>", lambda ev: go())

    def display_message(self, text):
        self.chat_area.config(state=tk.NORMAL)
        self.chat_area.insert(tk.END, str(text) + "\n\n")
        self.chat_area.see(tk.END)
        self.chat_area.config(state=tk.DISABLED)
        if not text.startswith("++++ Choose"):
            self.chat_log.append({"role": "system", "text": str(text)})
            if len(self.chat_log) > self.max_chat_log:
                self.chat_log = self.chat_log[-self.max_chat_log:]

    def display_image(self, image_data, filename=None):
        try:
            img = Image.open(io.BytesIO(image_data))
            if img.width > 400:
                ratio = 400 / img.width
                try:
                    resample = Image.Resampling.LANCZOS
                except AttributeError:
                    resample = Image.LANCZOS
                img = img.resize((400, int(img.height * ratio)), resample)
            photo = ImageTk.PhotoImage(img)
            self.image_cache.append(photo)
            self.chat_area.config(state=tk.NORMAL)
            self.chat_area.insert(tk.END, "[Generated Image]\n")
            self.chat_area.image_create(tk.END, image=photo)
            self.chat_area.insert(tk.END, "\n")
            if filename:
                self.chat_area.insert(tk.END, f"[saved: {filename}]\n\n")
            self.chat_area.see(tk.END)
            self.chat_area.config(state=tk.DISABLED)
        except Exception as e:
            self.display_message(f"[Image] saved to {filename} ({e})")

    def get_recent_messages(self, count=30):
        lines = []
        for entry in self.chat_log:
            t = entry["text"].strip()
            if not t:
                continue
            if t.startswith(("[Summary]", "[Keywords]", "[Image]", "[AI]",
                             "---", "++++", "[Generated")):
                continue
            lines.append(t)
        return "\n".join(lines[-count:])

    def show_summary(self):
        if self.ai_bot is None:
            self.display_message("[Summary] AI not available"); return
        recent = self.get_recent_messages(30)
        if not recent.strip():
            self.display_message("[Summary] not enough messages"); return
        self.display_message("[Summary] generating...")

        def work():
            try:
                s = self.ai_bot.summarize_chat(recent)
            except Exception as e:
                s = f"error: {e}"
            self.root.after(0, lambda: self.display_message(f"[SUMMARY]\n{s}"))
        threading.Thread(target=work, daemon=True).start()

    def show_keywords(self):
        if self.ai_bot is None:
            self.display_message("[Keywords] AI not available"); return
        recent = self.get_recent_messages(30)
        if not recent.strip():
            self.display_message("[Keywords] not enough messages"); return
        self.display_message("[Keywords] extracting...")

        def work():
            try:
                k = self.ai_bot.extract_keywords(recent)
            except Exception as e:
                k = f"error: {e}"
            self.root.after(0, lambda: self.display_message(f"[KEYWORDS]\n{k}"))
        threading.Thread(target=work, daemon=True).start()

    def show_rooms(self):
        self.send_command("/rooms")

    def toggle_sentiment(self):
        self.sentiment_enabled = not self.sentiment_enabled
        self.display_message(f"[Sentiment] {'ON' if self.sentiment_enabled else 'OFF'}")

    def poll_messages(self):
        if not self.running:
            return
        try:
            r, _, _ = select.select([self.socket], [], [], 0)
            if self.socket in r:
                raw = self.recv()
                if raw:
                    out = self.sm.proc("", raw)
                    if out:
                        skip = any(out.startswith(p) for p in SKIP_SENTIMENT_PREFIXES)
                        if self.ai_bot and self.sentiment_enabled and not skip:
                            def analyze(text):
                                try:
                                    _, emoji = self.ai_bot.analyze_sentiment(text)
                                except Exception:
                                    emoji = ""
                                self.root.after(0, lambda: self.display_message(f"{emoji} {text}"))
                            threading.Thread(target=analyze, args=(out,),
                                             daemon=True).start()
                        else:
                            self.display_message(out)

            if self.my_msg:
                out = self.sm.proc(self.my_msg, "")
                self.my_msg = ""
                if self.sm.get_state() == S_OFFLINE:
                    self.on_closing()
                    return
                if out:
                    self.display_message(out)
        except Exception as e:
            print("poll error:", e)
        if self.running:
            self.after_id = self.root.after(100, self.poll_messages)

    def on_closing(self):
        self.running = False
        if self.after_id:
            try:
                self.root.after_cancel(self.after_id)
            except Exception:
                pass
        try:
            self.sm.proc("q", "")
        except Exception:
            pass
        try:
            if self.socket:
                self.socket.close()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self):
        self.show_login()