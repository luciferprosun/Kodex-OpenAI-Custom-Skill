"""Minimal RFC 6455 text transport for localhost Codex App Server traffic.

The installed App Server protocol uses one JSON-RPC message per WebSocket text
frame. This module deliberately implements only that transport surface plus
the control frames required for a well-behaved WebSocket peer.
"""
from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
import hashlib
import ipaddress
import os
from typing import Awaitable, Callable
from urllib.parse import urlsplit


GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_HTTP_HEADER = 64 * 1024
MAX_MESSAGE_SIZE = 16 * 1024 * 1024


class WebSocketError(RuntimeError):
    pass


class WebSocketClosed(WebSocketError):
    pass


def _is_loopback(host: str | None) -> bool:
    if host is None:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


async def _read_http_headers(reader: asyncio.StreamReader) -> tuple[str, dict[str, str]]:
    try:
        raw = await reader.readuntil(b"\r\n\r\n")
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError) as exc:
        raise WebSocketError("incomplete WebSocket handshake") from exc
    if len(raw) > MAX_HTTP_HEADER:
        raise WebSocketError("WebSocket handshake headers are too large")
    try:
        lines = raw.decode("ascii").split("\r\n")
    except UnicodeDecodeError as exc:
        raise WebSocketError("WebSocket handshake is not ASCII") from exc
    start = lines[0]
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            continue
        if ":" not in line:
            raise WebSocketError("malformed WebSocket handshake header")
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    return start, headers


def _accept_value(key: str) -> str:
    return base64.b64encode(hashlib.sha1((key + GUID).encode("ascii")).digest()).decode("ascii")


@dataclass(frozen=True)
class _Frame:
    fin: bool
    opcode: int
    payload: bytes


class WebSocketConnection:
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        mask_outgoing: bool,
        expect_masked: bool,
    ):
        self.reader = reader
        self.writer = writer
        self.mask_outgoing = mask_outgoing
        self.expect_masked = expect_masked
        self._write_lock = asyncio.Lock()
        self._closed = False
        self._fragment_opcode: int | None = None
        self._fragments = bytearray()

    async def recv_text(self) -> str:
        while True:
            frame = await self._read_frame()
            if frame.opcode == 0x8:
                if not self._closed:
                    await self._write_frame(0x8, frame.payload[:125])
                self._closed = True
                raise WebSocketClosed("WebSocket peer closed the connection")
            if frame.opcode == 0x9:
                await self._write_frame(0xA, frame.payload)
                continue
            if frame.opcode == 0xA:
                continue
            if frame.opcode == 0x2:
                await self.close(code=1003, reason="text frames required")
                raise WebSocketError("binary WebSocket messages are unsupported")
            if frame.opcode == 0x1:
                if self._fragment_opcode is not None:
                    raise WebSocketError("new data frame during fragmented message")
                if frame.fin:
                    return self._decode_text(frame.payload)
                self._fragment_opcode = frame.opcode
                self._fragments.extend(frame.payload)
                continue
            if frame.opcode == 0x0:
                if self._fragment_opcode is None:
                    raise WebSocketError("unexpected continuation frame")
                self._fragments.extend(frame.payload)
                if len(self._fragments) > MAX_MESSAGE_SIZE:
                    raise WebSocketError("fragmented WebSocket message is too large")
                if frame.fin:
                    payload = bytes(self._fragments)
                    opcode = self._fragment_opcode
                    self._fragments.clear()
                    self._fragment_opcode = None
                    if opcode != 0x1:
                        raise WebSocketError("fragmented binary message is unsupported")
                    return self._decode_text(payload)
                continue
            raise WebSocketError("unsupported WebSocket opcode")

    async def send_text(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("WebSocket text payload must be a string")
        await self._write_frame(0x1, value.encode("utf-8"))

    async def close(self, *, code: int = 1000, reason: str = "") -> None:
        was_closed = self._closed
        self._closed = True
        if not was_closed:
            payload = code.to_bytes(2, "big") + reason.encode("utf-8")[:123]
            try:
                await self._write_frame(0x8, payload)
            except (OSError, WebSocketError):
                pass
        self.writer.close()
        try:
            await self.writer.wait_closed()
        except OSError:
            pass

    async def _read_frame(self) -> _Frame:
        try:
            first, second = await self.reader.readexactly(2)
        except (asyncio.IncompleteReadError, ConnectionError) as exc:
            self._closed = True
            raise WebSocketClosed("WebSocket connection ended") from exc
        fin = bool(first & 0x80)
        if first & 0x70:
            raise WebSocketError("WebSocket extensions were not negotiated")
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        if masked != self.expect_masked:
            raise WebSocketError("WebSocket masking direction is invalid")
        length = second & 0x7F
        if length == 126:
            length = int.from_bytes(await self.reader.readexactly(2), "big")
        elif length == 127:
            encoded = await self.reader.readexactly(8)
            if encoded[0] & 0x80:
                raise WebSocketError("invalid WebSocket frame length")
            length = int.from_bytes(encoded, "big")
        if length > MAX_MESSAGE_SIZE:
            raise WebSocketError("WebSocket message is too large")
        if opcode >= 0x8 and (not fin or length > 125):
            raise WebSocketError("invalid WebSocket control frame")
        mask = await self.reader.readexactly(4) if masked else b""
        payload = await self.reader.readexactly(length)
        if masked:
            payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        return _Frame(fin=fin, opcode=opcode, payload=payload)

    async def _write_frame(self, opcode: int, payload: bytes) -> None:
        if self.writer.is_closing() and opcode != 0x8:
            raise WebSocketClosed("WebSocket connection is closed")
        first = 0x80 | opcode
        length = len(payload)
        mask_bit = 0x80 if self.mask_outgoing else 0
        if length < 126:
            header = bytes([first, mask_bit | length])
        elif length <= 0xFFFF:
            header = bytes([first, mask_bit | 126]) + length.to_bytes(2, "big")
        else:
            header = bytes([first, mask_bit | 127]) + length.to_bytes(8, "big")
        if self.mask_outgoing:
            mask = os.urandom(4)
            payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
            encoded = header + mask + payload
        else:
            encoded = header + payload
        async with self._write_lock:
            self.writer.write(encoded)
            try:
                await self.writer.drain()
            except (ConnectionError, OSError) as exc:
                raise WebSocketClosed("WebSocket write failed") from exc

    @staticmethod
    def _decode_text(payload: bytes) -> str:
        try:
            return payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WebSocketError("WebSocket text frame is not UTF-8") from exc


async def connect_websocket(url: str) -> WebSocketConnection:
    parsed = urlsplit(url)
    if parsed.scheme != "ws" or not _is_loopback(parsed.hostname):
        raise WebSocketError("only localhost ws:// endpoints are allowed")
    if parsed.username is not None or parsed.password is not None:
        raise WebSocketError("credentials in WebSocket URLs are forbidden")
    port = parsed.port
    if port is None:
        raise WebSocketError("WebSocket endpoint must include a port")
    reader, writer = await asyncio.open_connection(parsed.hostname, port)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    host_header = f"{parsed.hostname}:{port}"
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host_header}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    writer.write(request.encode("ascii"))
    await writer.drain()
    start, headers = await _read_http_headers(reader)
    if not start.startswith("HTTP/1.1 101 "):
        writer.close()
        raise WebSocketError("WebSocket backend rejected the handshake")
    if headers.get("sec-websocket-accept") != _accept_value(key):
        writer.close()
        raise WebSocketError("WebSocket backend returned an invalid accept key")
    return WebSocketConnection(
        reader,
        writer,
        mask_outgoing=True,
        expect_masked=False,
    )


ClientHandler = Callable[[WebSocketConnection], Awaitable[None]]


class WebSocketServer:
    def __init__(self, host: str, port: int, handler: ClientHandler):
        if host != "127.0.0.1":
            raise WebSocketError("routing proxy must bind exactly to 127.0.0.1")
        self.host = host
        self.port = port
        self.handler = handler
        self._server: asyncio.AbstractServer | None = None

    @property
    def bound_port(self) -> int:
        if self._server is None or not self._server.sockets:
            raise WebSocketError("WebSocket server is not running")
        return int(self._server.sockets[0].getsockname()[1])

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._accept, self.host, self.port)

    async def close(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    async def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        connection: WebSocketConnection | None = None
        try:
            start, headers = await _read_http_headers(reader)
            parts = start.split(" ")
            if len(parts) != 3 or parts[0] != "GET":
                raise WebSocketError("invalid WebSocket request line")
            path = parts[1]
            if path in {"/readyz", "/healthz"} and "upgrade" not in headers:
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK")
                await writer.drain()
                return
            if "origin" in headers:
                writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                await writer.drain()
                return
            if headers.get("upgrade", "").lower() != "websocket":
                raise WebSocketError("missing WebSocket upgrade header")
            if "upgrade" not in headers.get("connection", "").lower():
                raise WebSocketError("missing WebSocket connection upgrade")
            if headers.get("sec-websocket-version") != "13":
                raise WebSocketError("unsupported WebSocket version")
            key = headers.get("sec-websocket-key")
            if key is None:
                raise WebSocketError("missing WebSocket key")
            try:
                if len(base64.b64decode(key, validate=True)) != 16:
                    raise ValueError
            except ValueError as exc:
                raise WebSocketError("invalid WebSocket key") from exc
            response = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {_accept_value(key)}\r\n\r\n"
            )
            writer.write(response.encode("ascii"))
            await writer.drain()
            connection = WebSocketConnection(
                reader,
                writer,
                mask_outgoing=False,
                expect_masked=True,
            )
            await self.handler(connection)
        except (WebSocketClosed, asyncio.CancelledError):
            pass
        except (WebSocketError, OSError):
            if not writer.is_closing():
                writer.close()
        finally:
            if connection is not None:
                await connection.close()
            elif not writer.is_closing():
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass
