# Multi-user Chat (Python course final project)

A multi-user chat server and client implementing the **baseline project**:
one chat room where every *writer* message is delivered to every *reader*.

## Files

- `common.py` — code shared by both programs: the default port and the
  line-delimited JSON wire protocol (plus a `LineBuffer` that reassembles
  TCP frames).
- `server.py` — the chat server. A single `select.select` loop over
  non-blocking sockets (no threads) accepts any number of clients, relays
  writer messages to all readers, and appends every message to a CSV log.
- `client.py` — the chat client, in either **writer** or **reader** mode.

## Requirements

Python 3 standard library only — nothing to install.

> Note: the handout specifies `raw_input` (Python 2). This implementation
> targets Python 3 and uses the equivalent `input`.

## Usage

Start the server:

```
python3 server.py [-p PORT] [-l LOG]
    -p PORT   Port to listen on (default: 7777)
    -l LOG    Log file (default: log.csv)
```

Connect clients (one mode per client):

```
python3 client.py -u USERNAME [-s SERVER] [-p PORT]   # writer: type messages
python3 client.py -r          [-s SERVER] [-p PORT]   # reader: see messages
    -s SERVER   Server address or host name (default: localhost)
    -p PORT     Port to connect to (default: 7777)
```

A writer types lines and presses Enter to send each one. A reader prints
every message as `[<date time>] <username>: <message>`. Press **Ctrl-C** to
disconnect and quit. The server also stops on **Ctrl-C**, closing the log
file first so no data is lost.

### Commands

A line starting with `/` is a command instead of chat text. Currently
supported:

```
/file PATH   Send the file at PATH to the chat (5 MiB limit)
```

Commands are registered in a small dict in `client.py` (see the
`@command("name")` decorator), so adding another one later (e.g. `/nick`,
`/quit`) doesn't require changing the writer's input loop.

A reader that receives a file saves it to a local `received_files/`
folder (created automatically) and prints a line like:

```
[2026-07-13 10:00:00] alice sent a file: photo.png (48213 bytes) -> saved to received_files/photo.png
```

If a file with the same name already exists, the new one is saved as
`name_1.ext`, `name_2.ext`, etc. rather than overwriting anything.

## Tests

Unit tests live in `test_chat.py` and run with **pytest**:

```
pip install pytest
pytest
```

They cover the wire protocol and `LineBuffer`, CSV logging (header creation
and append), broadcast-to-readers-only, the read/write/drop socket paths
(via fake sockets — no real networking needed) and argument parsing.

## Example

```
# terminal 1
python3 server.py

# terminal 2
python3 client.py -r

# terminal 3
python3 client.py -u alice
```

Anything typed in terminal 3 appears in terminal 2 and is logged to
`log.csv` (columns: Username, DateTime, Message).
```
