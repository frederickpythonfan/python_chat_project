"""Pytest unit tests for the chat project.

These tests exercise the pure logic of ``common``, ``server`` and
``client`` without opening real sockets, so they run in any environment
(including sandboxes that block networking).  The server's socket-facing
methods are driven with small fake socket objects that record what was
sent and replay canned ``recv`` data.

Run with::

    pytest
"""

import csv
import json

import pytest

import common
import server
import client


# --------------------------------------------------------------------------
# Test doubles
# --------------------------------------------------------------------------

class FakeSocket(object):
    """Minimal stand-in for a socket used by the server.

    Records everything written via ``send`` and, optionally, returns
    queued chunks from ``recv``.  ``send`` can be told to accept only a
    fixed number of bytes per call to exercise partial-send handling.
    """

    def __init__(self, recv_chunks=None, send_limit=None):
        self.sent = b""
        self.closed = False
        self._recv_chunks = list(recv_chunks or [])
        self._send_limit = send_limit

    def send(self, data):
        if self._send_limit is not None:
            data = data[:self._send_limit]
        self.sent += data
        return len(data)

    def recv(self, _bufsize):
        if self._recv_chunks:
            return self._recv_chunks.pop(0)
        return b""

    def close(self):
        self.closed = True


def decode_frames(blob):
    """Decode concatenated newline-delimited JSON frames into objects."""
    return [json.loads(line) for line in blob.decode("utf-8").splitlines()]


@pytest.fixture
def chat_server(tmp_path):
    """A ChatServer with an open CSV log in a temp dir (no sockets)."""
    log_path = tmp_path / "log.csv"
    srv = server.ChatServer(port=7777, log_path=str(log_path))
    srv.open_log()
    yield srv, log_path
    srv.log_file.close()


def make_state(mode=None, username=None, recv_chunks=None, send_limit=None):
    """Build a ClientState wrapping a FakeSocket."""
    sock = FakeSocket(recv_chunks=recv_chunks, send_limit=send_limit)
    state = server.ClientState(sock, ("127.0.0.1", 5555))
    state.mode = mode
    state.username = username
    return state


# --------------------------------------------------------------------------
# common.py
# --------------------------------------------------------------------------

class TestEncodeAndBuilders(object):
    def test_encode_is_newline_terminated_utf8(self):
        blob = common.encode({"type": "x"})
        assert blob.endswith(b"\n")
        assert json.loads(blob.decode("utf-8")) == {"type": "x"}

    def test_encode_roundtrips_unicode(self):
        blob = common.encode(common.make_msg("שלום, мир, 🎉"))
        assert json.loads(blob.decode("utf-8"))["text"] == "שלום, мир, 🎉"

    def test_make_hello_writer(self):
        assert common.make_hello(common.MODE_WRITER, "alice") == {
            "type": common.TYPE_HELLO,
            "mode": common.MODE_WRITER,
            "username": "alice",
        }

    def test_make_hello_reader_has_no_username(self):
        hello = common.make_hello(common.MODE_READER)
        assert hello["mode"] == common.MODE_READER
        assert hello["username"] is None

    def test_make_msg(self):
        assert common.make_msg("hi") == {"type": common.TYPE_MSG, "text": "hi"}

    def test_make_chat(self):
        chat = common.make_chat("bob", "2026-06-28 10:00:00", "hello")
        assert chat == {
            "type": common.TYPE_CHAT,
            "username": "bob",
            "timestamp": "2026-06-28 10:00:00",
            "text": "hello",
        }

    def test_format_chat_line(self):
        line = common.format_chat_line("bob", "2026-06-28 10:00:00", "hello")
        assert line == "[2026-06-28 10:00:00] bob: hello"


class TestLineBuffer(object):
    def test_single_complete_frame(self):
        buf = common.LineBuffer()
        assert buf.feed(common.encode(common.make_msg("hi"))) == [
            {"type": common.TYPE_MSG, "text": "hi"}
        ]

    def test_multiple_frames_in_one_chunk(self):
        buf = common.LineBuffer()
        raw = common.encode(common.make_msg("a")) + \
              common.encode(common.make_msg("b"))
        assert [m["text"] for m in buf.feed(raw)] == ["a", "b"]

    def test_frame_split_across_chunks(self):
        buf = common.LineBuffer()
        raw = common.encode(common.make_msg("hello, world"))
        assert buf.feed(raw[:5]) == []          # partial -> nothing yet
        msgs = buf.feed(raw[5:])                 # remainder completes it
        assert [m["text"] for m in msgs] == ["hello, world"]

    def test_partial_frame_is_retained_between_feeds(self):
        buf = common.LineBuffer()
        raw = common.encode({"type": "x"})
        # Feed one byte at a time; only the final byte yields the message.
        results = [buf.feed(raw[i:i + 1]) for i in range(len(raw))]
        assert results[-1] == [{"type": "x"}]
        assert all(r == [] for r in results[:-1])

    def test_malformed_frame_is_ignored(self):
        buf = common.LineBuffer()
        assert buf.feed(b"this is not json\n") == []

    def test_malformed_frame_does_not_drop_valid_neighbour(self):
        buf = common.LineBuffer()
        assert buf.feed(b"garbage\n{\"type\": \"ok\"}\n") == [{"type": "ok"}]

    def test_blank_lines_are_skipped(self):
        buf = common.LineBuffer()
        assert buf.feed(b"\n\n") == []


# --------------------------------------------------------------------------
# server.py
# --------------------------------------------------------------------------

class TestServerLog(object):
    def test_open_log_writes_header_for_new_file(self, tmp_path):
        log_path = tmp_path / "fresh.csv"
        srv = server.ChatServer(7777, str(log_path))
        srv.open_log()
        srv.log_file.close()
        rows = list(csv.reader(open(str(log_path))))
        assert rows == [["Username", "DateTime", "Message"]]

    def test_open_log_appends_without_duplicate_header(self, tmp_path):
        log_path = tmp_path / "existing.csv"
        log_path.write_text("Username,DateTime,Message\nalice,t,old\n")
        srv = server.ChatServer(7777, str(log_path))
        srv.open_log()
        srv.log_file.close()
        rows = list(csv.reader(open(str(log_path))))
        # Header appears exactly once; previous data preserved.
        assert rows[0] == ["Username", "DateTime", "Message"]
        assert rows.count(["Username", "DateTime", "Message"]) == 1
        assert rows[1] == ["alice", "t", "old"]


class TestHandleChat(object):
    def test_chat_is_logged_to_csv(self, chat_server):
        srv, log_path = chat_server
        writer = make_state(common.MODE_WRITER, "alice")
        srv.clients = {writer.sock: writer}
        srv._handle_chat(writer, "hello, world")
        srv.log_file.flush()
        rows = list(csv.reader(open(str(log_path))))
        assert rows[0] == ["Username", "DateTime", "Message"]
        assert rows[1][0] == "alice"
        assert rows[1][2] == "hello, world"     # comma survives CSV quoting

    def test_broadcast_goes_to_readers_only(self, chat_server):
        srv, _ = chat_server
        reader = make_state(common.MODE_READER)
        writer = make_state(common.MODE_WRITER, "alice")
        srv.clients = {reader.sock: reader, writer.sock: writer}
        srv._handle_chat(writer, "hi there, friend")

        frames = decode_frames(reader.outgoing)
        assert frames[0]["type"] == common.TYPE_CHAT
        assert frames[0]["username"] == "alice"
        assert frames[0]["text"] == "hi there, friend"
        # The writer must never receive its own (or any) broadcast.
        assert writer.outgoing == b""

    def test_broadcast_reaches_multiple_readers(self, chat_server):
        srv, _ = chat_server
        r1 = make_state(common.MODE_READER)
        r2 = make_state(common.MODE_READER)
        writer = make_state(common.MODE_WRITER, "alice")
        srv.clients = {r1.sock: r1, r2.sock: r2, writer.sock: writer}
        srv._handle_chat(writer, "broadcast")
        assert decode_frames(r1.outgoing)[0]["text"] == "broadcast"
        assert decode_frames(r2.outgoing)[0]["text"] == "broadcast"

    def test_username_falls_back_to_anonymous(self, chat_server):
        srv, log_path = chat_server
        writer = make_state(common.MODE_WRITER, username=None)
        srv.clients = {writer.sock: writer}
        srv._handle_chat(writer, "nameless")
        srv.log_file.flush()
        rows = list(csv.reader(open(str(log_path))))
        assert rows[1][0] == "anonymous"


class TestDispatch(object):
    def test_hello_sets_mode_and_username(self, chat_server):
        srv, _ = chat_server
        state = make_state()
        srv.clients = {state.sock: state}
        srv._dispatch(state, common.make_hello(common.MODE_WRITER, "alice"))
        assert state.mode == common.MODE_WRITER
        assert state.username == "alice"

    def test_msg_is_logged_and_broadcast(self, chat_server):
        srv, log_path = chat_server
        reader = make_state(common.MODE_READER)
        writer = make_state(common.MODE_WRITER, "alice")
        srv.clients = {reader.sock: reader, writer.sock: writer}
        srv._dispatch(writer, common.make_msg("via dispatch"))
        assert decode_frames(reader.outgoing)[0]["text"] == "via dispatch"
        srv.log_file.flush()
        assert list(csv.reader(open(str(log_path))))[1][2] == "via dispatch"

    def test_unknown_type_is_ignored(self, chat_server):
        srv, _ = chat_server
        reader = make_state(common.MODE_READER)
        srv.clients = {reader.sock: reader}
        srv._dispatch(reader, {"type": "bogus"})
        assert reader.outgoing == b""


class TestReadWriteDrop(object):
    def test_handle_read_dispatches_a_hello(self, chat_server):
        srv, _ = chat_server
        hello = common.encode(common.make_hello(common.MODE_WRITER, "alice"))
        state = make_state(recv_chunks=[hello])
        srv.clients = {state.sock: state}
        srv._handle_read(state.sock)
        assert state.mode == common.MODE_WRITER
        assert state.username == "alice"

    def test_handle_read_empty_recv_drops_client(self, chat_server):
        srv, _ = chat_server
        state = make_state(recv_chunks=[b""])     # peer closed connection
        srv.clients = {state.sock: state}
        srv._handle_read(state.sock)
        assert state.sock not in srv.clients
        assert state.sock.closed

    def test_handle_write_sends_and_clears_buffer(self, chat_server):
        srv, _ = chat_server
        state = make_state(common.MODE_READER)
        state.outgoing = b"hello"
        srv.clients = {state.sock: state}
        srv._handle_write(state.sock)
        assert state.sock.sent == b"hello"
        assert state.outgoing == b""

    def test_handle_write_partial_send_keeps_remainder(self, chat_server):
        srv, _ = chat_server
        state = make_state(common.MODE_READER, send_limit=3)
        state.outgoing = b"hello"
        srv.clients = {state.sock: state}
        srv._handle_write(state.sock)
        assert state.sock.sent == b"hel"
        assert state.outgoing == b"lo"           # leftover stays queued

    def test_drop_is_idempotent(self, chat_server):
        srv, _ = chat_server
        state = make_state(common.MODE_READER)
        srv.clients = {state.sock: state}
        srv._drop(state.sock)
        srv._drop(state.sock)                     # second call must not raise
        assert srv.clients == {}


class TestServerClose(object):
    def test_close_flushes_log_and_drops_clients(self, tmp_path):
        log_path = tmp_path / "log.csv"
        srv = server.ChatServer(7777, str(log_path))
        srv.open_log()
        state = make_state(common.MODE_READER)
        srv.clients = {state.sock: state}
        srv.close()
        assert state.sock.closed
        assert srv.log_file.closed


# --------------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------------

class TestServerArgs(object):
    def test_defaults(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["server.py"])
        args = server.parse_args()
        assert args.port == common.DEFAULT_PORT
        assert args.log == "log.csv"

    def test_custom_port_and_log(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["server.py", "-p", "9000", "-l", "x.csv"])
        args = server.parse_args()
        assert args.port == 9000
        assert args.log == "x.csv"


class TestClientArgs(object):
    def test_writer_mode(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["client.py", "-u", "alice"])
        args = client.parse_args()
        assert args.username == "alice"
        assert args.reader is False
        assert args.server == "localhost"
        assert args.port == common.DEFAULT_PORT

    def test_reader_mode_with_host_and_port(self, monkeypatch):
        monkeypatch.setattr(
            "sys.argv", ["client.py", "-r", "-s", "example.com", "-p", "8000"])
        args = client.parse_args()
        assert args.reader is True
        assert args.server == "example.com"
        assert args.port == 8000

    def test_both_modes_is_rejected(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["client.py", "-r", "-u", "alice"])
        with pytest.raises(SystemExit):
            client.main()

    def test_no_mode_is_rejected(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["client.py"])
        with pytest.raises(SystemExit):
            client.main()
