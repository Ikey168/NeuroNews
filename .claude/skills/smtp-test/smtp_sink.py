"""
Minimal async SMTP sink server.

Handles just enough of the SMTP protocol to accept a full message from
smtplib (EHLO, MAIL FROM, RCPT TO, DATA, QUIT). Captured messages are
stored in `MESSAGES` as dicts with keys: mail_from, rcpt_to, raw_data.

Usage (standalone):
    import asyncio, threading
    from smtp_sink import start_sink, MESSAGES, stop_sink
    port = start_sink()          # starts server in background thread
    # ... send mail to localhost:port ...
    msg = wait_for_message(timeout=10)
    stop_sink()
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Dict, List, Optional


MESSAGES: List[Dict[str, Any]] = []
_server: Optional[asyncio.Server] = None
_loop: Optional[asyncio.AbstractEventLoop] = None
_thread: Optional[threading.Thread] = None


class _SMTPHandler(asyncio.Protocol):
    def __init__(self) -> None:
        self._buf = b""
        self._state = "greeting"
        self._mail_from = ""
        self._rcpt_to: List[str] = []
        self._in_data = False
        self._data_lines: List[bytes] = []
        self._transport: Optional[asyncio.Transport] = None

    def connection_made(self, transport: asyncio.Transport) -> None:  # type: ignore[override]
        self._transport = transport
        self._send(b"220 smtp-sink ESMTP ready\r\n")

    def _send(self, data: bytes) -> None:
        if self._transport:
            self._transport.write(data)

    def data_received(self, data: bytes) -> None:
        self._buf += data
        while b"\r\n" in self._buf:
            line, self._buf = self._buf.split(b"\r\n", 1)
            self._handle_line(line)

    def _handle_line(self, line: bytes) -> None:
        if self._in_data:
            if line == b".":
                self._in_data = False
                raw = b"\r\n".join(self._data_lines)
                MESSAGES.append({
                    "mail_from": self._mail_from,
                    "rcpt_to": list(self._rcpt_to),
                    "raw_data": raw.decode("utf-8", errors="replace"),
                })
                self._send(b"250 OK\r\n")
            else:
                # Unstuff leading dots
                self._data_lines.append(line[1:] if line.startswith(b"..") else line)
            return

        cmd = line[:4].upper()
        if cmd in (b"EHLO", b"HELO"):
            self._send(b"250-smtp-sink\r\n250-8BITMIME\r\n250 OK\r\n")
        elif cmd == b"MAIL":
            self._mail_from = line.decode(errors="replace")
            self._rcpt_to = []
            self._send(b"250 OK\r\n")
        elif cmd == b"RCPT":
            self._rcpt_to.append(line.decode(errors="replace"))
            self._send(b"250 OK\r\n")
        elif cmd == b"DATA":
            self._in_data = True
            self._data_lines = []
            self._send(b"354 End data with <CR><LF>.<CR><LF>\r\n")
        elif cmd == b"QUIT":
            self._send(b"221 Bye\r\n")
            if self._transport:
                self._transport.close()
        elif cmd == b"RSET":
            self._mail_from = ""
            self._rcpt_to = []
            self._data_lines = []
            self._in_data = False
            self._send(b"250 OK\r\n")
        elif cmd == b"NOOP":
            self._send(b"250 OK\r\n")
        else:
            self._send(b"500 Unrecognised command\r\n")

    def connection_lost(self, exc: Optional[Exception]) -> None:  # noqa: U100
        pass


def start_sink(host: str = "127.0.0.1", port: int = 0) -> int:
    """
    Start the SMTP sink in a daemon thread.
    Returns the actual port it bound to (useful when port=0).
    """
    global _loop, _thread
    import socket

    # Find a free port if port=0
    if port == 0:
        with socket.socket() as s:
            s.bind((host, 0))
            port = s.getsockname()[1]

    _loop = asyncio.new_event_loop()
    ready = threading.Event()
    actual_port: List[int] = []

    def _run() -> None:
        asyncio.set_event_loop(_loop)

        async def _main() -> None:
            global _server
            _server = await _loop.create_server(lambda: _SMTPHandler(), host, port)
            actual_port.append(_server.sockets[0].getsockname()[1])
            ready.set()
            async with _server:
                await _server.serve_forever()

        _loop.run_until_complete(_main())

    _thread = threading.Thread(target=_run, daemon=True)
    _thread.start()
    ready.wait(timeout=5)
    return actual_port[0] if actual_port else port


def stop_sink() -> None:
    global _loop, _server
    if _loop and _server:
        _loop.call_soon_threadsafe(_server.close)


def wait_for_message(timeout: float = 10.0) -> Optional[Dict[str, Any]]:
    """Block until a message arrives or timeout. Returns the message or None."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if MESSAGES:
            return MESSAGES[-1]
        time.sleep(0.1)
    return None
