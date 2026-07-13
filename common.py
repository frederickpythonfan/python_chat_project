"""Shared code for the chat server and client.

Holds everything common to both ``server.py`` and ``client.py``:
the default port, the line-based JSON wire protocol, and a small
buffer helper for reassembling messages received over TCP.

Wire protocol
-------------
Every protocol unit is a single JSON object encoded as UTF-8 and
terminated by a newline (``\\n``).  Using one JSON object per line lets
chat text contain arbitrary characters (spaces, punctuation, etc.)
without us having to invent an escaping scheme for a field separator.

Message types
~~~~~~~~~~~~~
* hello  -- sent by a client right after connecting, announcing its
            mode ("writer" or "reader") and (for writers) its username.
* msg    -- sent by a writer client, carrying one line of chat text.
* chat   -- sent by the server to every reader, carrying the username,
            timestamp and text of a chat message.
"""

import base64
import json

# Default TCP port shared by the server (listen) and client (connect).
DEFAULT_PORT = 7777

# Client operating modes.
MODE_WRITER = "writer"
MODE_READER = "reader"

# Protocol message types.
TYPE_HELLO = "hello"
TYPE_MSG = "msg"
TYPE_CHAT = "chat"
TYPE_FILE_MSG = "file_msg"    # writer -> server: "here is a file"
TYPE_FILE_CHAT = "file_chat"  # server -> readers: broadcast of that file

# Timestamp format used both in the CSV log and on the wire.
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

_ENCODING = "utf-8"


def encode(obj):
    """Serialise a protocol object to a newline-terminated UTF-8 frame."""
    return (json.dumps(obj) + "\n").encode(_ENCODING)


def make_hello(mode, username=None):
    """Build the handshake message a client sends on connect."""
    return {"type": TYPE_HELLO, "mode": mode, "username": username}


def make_msg(text):
    """Build a chat message sent by a writer client."""
    return {"type": TYPE_MSG, "text": text}


def make_chat(username, timestamp, text):
    """Build a chat message the server broadcasts to readers."""
    return {
        "type": TYPE_CHAT,
        "username": username,
        "timestamp": timestamp,
        "text": text,
    }


def format_chat_line(username, timestamp, text):
    """Human-readable form a reader prints for one chat message."""
    return "[{0}] {1}: {2}".format(timestamp, username, text)


def make_file_msg(filename, data_b64):
    """Build a file message sent by a writer client.

    ``data_b64`` is the file's bytes, base64-encoded to a string so it
    can travel inside a JSON line like every other message on the wire.
    """
    return {"type": TYPE_FILE_MSG, "filename": filename, "data": data_b64}


def make_file_chat(username, timestamp, filename, data_b64):
    """Build a file message the server broadcasts to readers."""
    return {
        "type": TYPE_FILE_CHAT,
        "username": username,
        "timestamp": timestamp,
        "filename": filename,
        "data": data_b64,
    }


def format_file_line(username, timestamp, filename, size, saved_path):
    """Human-readable form a reader prints for one received file."""
    return "[{0}] {1} sent a file: {2} ({3} bytes) -> saved to {4}".format(
        timestamp, username, filename, size, saved_path)


def encode_file_data(raw_bytes):
    """Base64-encode raw file bytes into the string the wire protocol uses."""
    return base64.b64encode(raw_bytes).decode("ascii")


def decode_file_data(data_b64):
    """Reverse of :func:`encode_file_data`."""
    return base64.b64decode(data_b64.encode("ascii"))


class LineBuffer(object):
    """Reassembles newline-delimited JSON frames from a TCP byte stream.

    TCP is a stream, so a single ``recv`` may return part of a frame,
    exactly one frame, or several frames at once.  Feed raw bytes in
    with :meth:`feed` and get back the list of complete protocol
    objects that have arrived so far; any trailing partial frame is
    kept until the rest of it shows up.
    """

    def __init__(self):
        self._buffer = b""

    def feed(self, data):
        """Add received bytes and return a list of complete messages."""
        self._buffer += data
        messages = []
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line.decode(_ENCODING)))
            except (ValueError, UnicodeDecodeError):
                # Ignore malformed frames rather than crash the peer.
                continue
        return messages
