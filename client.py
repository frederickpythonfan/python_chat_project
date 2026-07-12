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
import socket
import sys

import common


def connect(server, port, hello):
    """Open a blocking TCP connection and send the handshake frame."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((server, port))
    sock.sendall(common.encode(hello))
    return sock


def run_writer(server, port, username):
    """Read lines from the user and send each to the server."""
    sock = connect(server, port, common.make_hello(common.MODE_WRITER, username))
    print("Connected as '%s' (writer). Type messages; Ctrl-C to quit."
          % username)
    try:
        while True:
            # raw_input in Python 2 / input in Python 3; we target Python 3.
            text = input()
            if text == "":
                continue
            sock.sendall(common.encode(common.make_msg(text)))
    except (EOFError, KeyboardInterrupt):
        print("\nDisconnecting...")
    except (socket.error, OSError) as exc:
        print("\nConnection lost: %s" % exc)
    finally:
        sock.close()


def run_reader(server, port):
    """Receive broadcast chat messages and print them as they arrive."""
    sock = connect(server, port, common.make_hello(common.MODE_READER))
    print("Connected (reader). Showing messages; Ctrl-C to quit.")
    buffer = common.LineBuffer()
    try:
        while True:
            data = sock.recv(4096)
            if not data:
                print("Server closed the connection.")
                break
            for message in buffer.feed(data):
                if message.get("type") == common.TYPE_CHAT:
                    print(common.format_chat_line(
                        message.get("username", "anonymous"),
                        message.get("timestamp", ""),
                        message.get("text", "")))
    except KeyboardInterrupt:
        print("\nDisconnecting...")
    except (socket.error, OSError) as exc:
        print("\nConnection lost: %s" % exc)
    finally:
        sock.close()


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
    args = parse_args()
    if args.reader and args.username:
        sys.exit("Error: choose either reader (-r) or writer (-u), not both.")
    if not args.reader and not args.username:
        sys.exit("Error: specify a mode: -u USERNAME (writer) or -r (reader).")

    try:
        if args.reader:
            run_reader(args.server, args.port)
        else:
            run_writer(args.server, args.port, args.username)
    except (socket.error, OSError) as exc:
        sys.exit("Could not connect to %s:%d -- %s"
                 % (args.server, args.port, exc))


if __name__ == "__main__":
    main()
