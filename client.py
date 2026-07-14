"""Chat client -- writer and reader modes.

A client connects to the chat server in exactly one of two modes, which
keeps each program single-purpose and avoids the need for threads:

* Writer (``-u USERNAME``): reads lines the user types and sends each
  one to the server as a chat message.
* Reader (``-r``): prints every chat message the server broadcasts,
  including the sender's username and the date+time.

Either way, the user quits by pressing Ctrl-C.

Usage::

    client.py [-u USERNAME] [-r] [-s SERVER] [-p PORT]

    -u USERNAME   Operate in writer mode, using USERNAME
    -r            Operate in reader mode
    -s SERVER     Server address or host name (default: localhost)
    -p PORT       Port to connect to (default: 7777)
"""

import argparse
import os
from pathlib import Path
import socket
import sys
from logging_config import setup_logging
import logging
logger = logging.getLogger(__name__)

import common
import decorators

# Cap on the size of a file sent with /file. The wire protocol packs the
# whole file into one base64 JSON line (see common.make_file_msg), so very
# large files would mean a very large in-memory line -- a future version
# could chunk/stream instead, but for typical chat attachments this is fine.
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MiB

# Where a reader saves files it receives.
RECEIVED_FILES_DIR = "received_files"

# ---------------------------------------------------------------------------
# Command dispatch
#
# A line typed in writer mode is either plain chat text, or -- if it starts
# with "/" -- a command. Commands are registered here by name and looked up
# by run_writer; adding a new one (e.g. a future /nick or /quit) never
# requires touching the writer loop, just defining a new handler below and
# decorating it with @command("name"). This is the same registry pattern
# text apps like Discord use for slash commands.
# ---------------------------------------------------------------------------

COMMANDS = {}

def command(name):
    """Register a writer-mode handler to run for '/<name> ...' input."""
    def register(func):
        COMMANDS[name] = func
        return func
    return register


@decorators.class_decorator(decorators.logging("client.calls"))
class ChatClient(object):
    def __init__(self, server_data : common.ServerValidation, username):
        self.server = server_data.HOST
        self.port = server_data.PORT
        self.username = username

    def connect(self, hello):
        """Open a blocking TCP connection and send the handshake frame."""
        logger.info("connecting to %s:%d as %s", self.server, self.port,
                    hello.get("mode"))
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((self.server, self.port))
        sock.sendall(common.encode(hello))
        logger.debug("handshake sent: %s", hello)
        return sock

    def dispatch_command(self, sock, text):
        """Try to run ``text`` (starting with "/") as a registered command.

        Returns True if a matching command handled it, False if the
        command name isn't recognized (so the caller can report that).
        """
        name, _, args = text[1:].partition(" ")
        handler = COMMANDS.get(name)
        if handler is None:
            logger.warning("unknown command: /%s", name)
            return False
        logger.debug("dispatching command /%s with args=%r", name, args)
        handler(self, sock, args)
        return True

    def run_writer(self):
        """Read lines from the user and send each to the server."""
        sock = self.connect(common.make_hello(common.MODE_WRITER, self.username))
        logger.info("writer session started for %s", self.username)
        print("Connected as '%s' (writer). Type messages; Ctrl-C to quit."
              % self.username)


        print("Commands: %s"
              % ", ".join("/%s" % name for name in sorted(COMMANDS)))
        try:
            while True:
                # raw_input in Python 2 / input in Python 3; we target Python 3.
                text = input()
                if text == "":
                    continue
                if text.startswith("/"):
                    if not self.dispatch_command(sock, text):
                        print("Unknown command: /%s" % text[1:].split(" ")[0])
                    continue
                logger.debug("sending chat message (%d char(s))", len(text))
                sock.sendall(common.encode(common.make_msg(text)))
        except (EOFError, KeyboardInterrupt):
            logger.info("writer session for %s ending (user requested)", self.username)
            print("\nDisconnecting...")
        except (socket.error, OSError) as exc:
            logger.error("writer session for %s lost connection: %s", self.username, exc)
            print("\nConnection lost: %s" % exc)
        finally:
            sock.close()
            logger.debug("writer socket closed")

    def run_reader(self):
        """Receive broadcast chat messages and print them as they arrive."""
        sock = self.connect(common.make_hello(common.MODE_READER))
        logger.info("reader session started")
        print("Connected (reader). Showing messages; Ctrl-C to quit.")
        buffer = common.LineBuffer()
        try:
            while True:
                data = sock.recv(4096)
                if not data:
                    logger.info("server closed the connection")
                    print("Server closed the connection.")
                    break
                logger.debug("received %d byte(s) from server", len(data))
                for message in buffer.feed(data):
                    msg_type = message.get("type")
                    logger.debug("received message type=%s", msg_type)
                    if msg_type == common.TYPE_CHAT:
                        print(common.format_chat_line(
                            message.get("username", "anonymous"),
                            message.get("timestamp", ""),
                            message.get("text", "")))
                    elif msg_type == common.TYPE_FILE_CHAT:
                        self._save_incoming_file(message)
                    elif msg_type == common.TYPE_RECOGNITION_CHAT:
                        print(common.format_recognition_line(
                            message.get("username", "anonymous"),
                            message.get("timestamp", ""),
                            message.get("filename", ""),
                            message.get("model_output")
                        ))
        except KeyboardInterrupt:
            logger.info("reader session ending (user requested)")
            print("\nDisconnecting...")
        except (socket.error, OSError) as exc:
            logger.error("reader session lost connection: %s", exc)
            print("\nConnection lost: %s" % exc)
        finally:
            sock.close()
            logger.debug("reader socket closed")

    def _save_incoming_file(self, message):
        """Decode and save a broadcast file message, then notify the user."""
        username = message.get("username", "anonymous")
        timestamp = message.get("timestamp", "")
        filename = message.get("filename") or "file"
        try:
            raw = common.decode_file_data(message.get("data", ""))
        except (ValueError, TypeError) as exc:
            logger.warning("corrupted file from %s ('%s'): %s", username, filename, exc)
            print("Received a corrupted file from %s; discarding." % username)
            return

        os.makedirs(RECEIVED_FILES_DIR, exist_ok=True)
        # basename() strips any directory components a peer might have sent
        # (e.g. "../../etc/passwd"), so a file always lands inside our folder.
        dest = _unique_path(
            os.path.join(RECEIVED_FILES_DIR, os.path.basename(filename)))
        with open(dest, "wb") as f:
            f.write(raw)
        logger.info("saved file from %s: '%s' (%d bytes) -> %s",
                    username, filename, len(raw), dest)
        print(common.format_file_line(username, timestamp, filename,
                                       len(raw), dest))


def _unique_path(path):
    """Return ``path``, or a "name_1.ext"-style variant if it already exists."""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while True:
        candidate = "%s_%d%s" % (base, i, ext)
        if not os.path.exists(candidate):
            return candidate
        i += 1


@command("recognize")
def cmd_file(chat_client, sock, args):
    """/recognize PATH -- recognize objects inside an image"""
    path = args.strip()
    if not path:
        logger.warning("/recognize called with no path")
        print("Usage: /recognize <path>")
        return
    filename = Path(RECEIVED_FILES_DIR) / path
    sock.sendall(common.encode(common.make_recognition_msg(filename)))
    logger.info("requested recognition for '%s'", filename)
    print(f"Asked to recognize {filename}")

@command("file")
def cmd_file(chat_client, sock, args):
    """/file PATH -- read a local file and send it to the chat."""
    path = args.strip()
    if not path:
        logger.warning("/file called with no path")
        print("Usage: /file <path>")
        return
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as exc:
        logger.error("couldn't read '%s': %s", path, exc)
        print("Couldn't read '%s': %s" % (path, exc))
        return
    if len(raw) > MAX_FILE_SIZE:
        logger.warning("'%s' is %d bytes, over the %d byte limit",
                        path, len(raw), MAX_FILE_SIZE)
        print("'%s' is %d bytes, over the %d byte limit."
              % (path, len(raw), MAX_FILE_SIZE))
        return

    filename = os.path.basename(path)
    data_b64 = common.encode_file_data(raw)
    sock.sendall(common.encode(common.make_file_msg(filename, data_b64)))
    logger.info("sent file '%s' (%d bytes)", filename, len(raw))
    print("Sent file '%s' (%d bytes)." % (filename, len(raw)))


def parse_args():
    parser = argparse.ArgumentParser(description="Chat client.")
    parser.add_argument("-u", "--username",
                        help="Operate in writer mode, using USERNAME")
    parser.add_argument("-r", "--reader", action="store_true",
                        help="Operate in reader mode")
    parser.add_argument("-s", "--server", default="localhost",
                        help="Server address or host name (default: localhost)")
    parser.add_argument("-p", "--port", type=int, default=common.DEFAULT_PORT,
                        help="Port to connect to (default: %d)"
                             % common.DEFAULT_PORT)
    return parser.parse_args()


def main():
    setup_logging()
    args = parse_args()
    if args.reader and args.username:
        logger.error("both reader and writer mode requested -- aborting")
        sys.exit("Error: choose either reader (-r) or writer (-u), not both.")
    if not args.reader and not args.username:
        logger.error("no mode specified -- aborting")
        sys.exit("Error: specify a mode: -u USERNAME (writer) or -r (reader).")

    class ClientData(metaclass=common.ServerValidation):
        HOST = args.server
        PORT = args.port
    logger.info("starting client, target=%s:%d, mode=%s",
                ClientData.HOST, ClientData.PORT,
                "reader" if args.reader else "writer")
    client = ChatClient(ClientData, args.username)
    try:
        if args.reader:
            client.run_reader()
        else:
            client.run_writer()
    except (socket.error, OSError) as exc:
        logger.error("could not connect to %s:%d -- %s",
                     ClientData.HOST, ClientData.PORT, exc)
        sys.exit("Could not connect to %s:%d -- %s"
                 % (ClientData.HOST, ClientData.PORT, exc))


if __name__ == "__main__":
    main()
