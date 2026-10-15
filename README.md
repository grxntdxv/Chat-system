![tests](https://github.com/grxntdxv/Chat-system/actions/workflows/tests.yml/badge.svg)

# Chat System

A small chat system written in Python. Async server, SQLite for storage,
a Tkinter GUI client, a CLI client, and an AI bot that can talk to users
through Ollama.

## What's inside

- `chat_server.py` - async TCP server
- `chat_protocol.py` - JSON message format
- `chat_utils.py` - wire framing helpers
- `storage.py` - SQLite (users, rooms, messages)
- `chat_group.py` - room membership
- `indexer.py` - search index and sonnet lookup
- `local_ai.py` - Ollama wrapper (chat, image, summary, keywords, sentiment)
- `chat_client.py` + `client_state_machine.py` - client core
- `chat_cmdl_client.py` - terminal client
- `GUI.py` + `gui_client.py` - Tkinter client
- `chat_bot_client.py` - bot that joins as `Chatbot`
- `tests/` - pytest suite

## Setup

```
pip3 install -r requirements.txt
```

## Run the server

```
python3 chat_server.py
```

Listens on `127.0.0.1:1112`. Creates `chat.db` on first run.

## Run a client

Terminal:

```
python3 chat_cmdl_client.py
```

GUI:

```
python3 gui_client.py
```

Bot (needs Ollama running):

```
python3 chat_b