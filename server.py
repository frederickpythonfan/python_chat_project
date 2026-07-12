"""Multi-user chat server.

Listens on a TCP port, accepts any number of chat clients, and relays
every message a *writer* sends to every connected *reader*.  All chat
messages are appended to a CSV log (username, date+time, message).

Concurrency is handled with a single ``select.select`` loop over
non-blocking sockets -- no threads.  The server runs until the operator
presses Ctrl-C, at which point it flushes and closes the log file so no
chat data is lost.

Usage::

    server.py [-p PORT] [-l LOG]

    -p PORT   Port to listen on (default: 7777)
    -l LOG    Log file (default: log.csv)
"""

import argparse
import csv
import datetime
import select
import socket

import common


class ClientState(object):
    """Per-connection bookkeeping the server keeps for each socket."""

    def __init__(self, sock, addr):
        self.sock = sock
        self.addr = addr
        self.buffer = common.LineBuffer()   # reassembles inbound frames
        self.outgoing = b""                 # bytes queued to send
        self.mode = None                    # writer / reader, set on hello
        self.username = None


class ChatServer(object):
    def __init__(self, port, log_path):
        self.port = port
        self.log_path = log_path
        self.clients = {}          # socket -> ClientState
        self.listen_sock = None
        self.log_file = None
        self.log_writer = None

    # -- setup / teardown -------------------------------------------------

    def open_log(self):
        """Open the CSV log for appending and write a header if new."""
        # newline="" is the documented way to use csv on all platforms.
        need_header = False
        try:
            with open(self.log_path, "r"):
                pass
        except IOError:
            need_header = True
        self.log_file = open(self.log_path, "a", newline="")
        self.log_writer = csv.writer(self.log_file)
        if need_header:
            self.log_writer.writerow(["Username", "DateTime", "Message"])
            self.log_file.flush()

    def open_socket(self):
        """Create the listening socket in non-blocking mode."""
        self.listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listen_sock.bind(("", self.port))
        self.listen_sock.listen(5)
        self.listen_sock.setblocking(False)

    def close(self):
        """Close all client sockets, the listener, and the log file."""
        for state in list(self.clients.values()):
            self._drop(state.sock)
        if self.listen_sock is not None:
            self.listen_sock.close()
        if self.log_file is not None:
            self.log_file.flush()
            self.log_file.close()

    # -- main loop --------------------------------------------------------

    def run(self):
        self.open_log()
        self.open_socket()
        print("Chat server listening on port %d (logging to %s)"
              % (self.port, self.log_path))
        print("Press Ctrl-C to stop.")
        while True:
            read_socks = [self.listen_sock] + list(self.clients)
            write_socks = [s for s, st in self.clients.items() if st.outgoing]
            readable, writable, _ = select.select(
                read_socks, write_socks, [])

            for sock in readable:
                if sock is self.listen_sock:
                    self._accept()
                else:
                    self._handle_read(sock)

            for sock in writable:
                self._handle_write(sock)

    # -- socket events ----------------------------------------------------

    def _accept(self):
        try:
            conn, addr = self.listen_sock.accept()
        except (socket.error, OSError):
            return
        conn.setblocking(False)
        self.clients[conn] = ClientState(conn, addr)

    def _handle_read(self, sock):
        try:
            data = sock.recv(4096)
        except (socket.error, OSError):
            self._drop(sock)
            return
        if not data:
            # Peer closed the connection cleanly.
            self._drop(sock)
            return
        state = self.clients[sock]
        for message in state.buffer.feed(data):
            self._dispatch(state, message)

    def _handle_write(self, sock):
        state = self.clients.get(sock)
        if state is None or not state.outgoing:
            return
        try:
            sent = sock.send(state.outgoing)
        except (socket.error, OSError):
            self._drop(sock)
            return
        state.outgoing = state.outgoing[sent:]

    # -- protocol handling ------------------------------------------------

    def _dispatch(self, state, message):
        msg_type = message.get("type")
        if msg_type == common.TYPE_HELLO:
            state.mode = message.get("mode")
            state.username = message.get("username")
            who = state.username or "reader"
            print("Client connected: %s (%s) from %s"
                  % (who, state.mode, state.addr[0]))
        elif msg_type == common.TYPE_MSG:
            self._handle_chat(state, message.get("text", ""))

    def _handle_chat(self, state, text):
        """Log an incoming chat line and fan it out to all readers."""
        username = state.username or "anonymous"
        timestamp = datetime.datetime.now().strftime(common.TIME_FORMAT)

        # Persist to the CSV log first so nothing is lost on a crash.
        self.log_writer.writerow([username, timestamp, text])
        self.log_file.flush()

        frame = common.encode(common.make_chat(username, timestamp, text))
        for other in self.clients.values():
            if other.mode == common.MODE_READER:
                other.outgoing += frame

    def _drop(self, sock):
        """Remove and close a client socket."""
        state = self.clients.pop(sock, None)
        if state is not None and state.username:
            print("Client disconnected: %s" % state.username)
        try:
            sock.close()
        except (socket.error, OSError):
            pass


def parse_args():
    parser = argparse.ArgumentParser(description="Multi-user chat server.")
    parser.add_argument("-p", "--port", type=int, default=common.DEFAULT_PORT,
                        help="Port to listen on (default: %d)"
                             % common.DEFAULT_PORT)
    parser.add_argument("-l", "--log", default="log.csv",
                        help="Log file (default: log.csv)")
    return parser.parse_args()


def main():
    args = parse_args()
    server = ChatServer(args.port, args.log)
    try:
        server.run()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.close()
        print("Log file closed. Bye.")


if __name__ == "__main__":
    main()
