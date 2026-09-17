"""
Minimal AWS EventStream decoder — extracts the JSON payloads from the binary
framing used by Amazon CodeWhisperer's `generateAssistantResponse`.

Frame layout (big-endian):
    4 bytes  total_len
    4 bytes  headers_len
    4 bytes  prelude_crc32
    headers  (headers_len bytes, key/value TLV — skipped)
    payload  (total_len - headers_len - 16 bytes)
    4 bytes  message_crc32

CodeWhisperer replies with multiple `assistantResponseEvent` frames whose
payloads carry `{"content": "..."}` fragments. This parser never validates
CRCs (the TLS channel already gives integrity).
"""

import logging
import struct

logger = logging.getLogger(__name__)


class EventStreamError(Exception):
    """Raised when the binary frame is malformed."""


def iter_eventstream_payloads(data: bytes):
    """Yield each payload's raw bytes from an EventStream byte buffer."""
    offset = 0
    total = len(data)

    while offset + 16 <= total:
        total_len, headers_len = struct.unpack_from(">II", data, offset)

        if total_len < 16 or offset + total_len > total:
            raise EventStreamError(
                f"Bad frame at offset {offset}: total_len={total_len} (buffer={total})"
            )

        prelude_crc = struct.unpack_from(">I", data, offset + 8)[0]
        prelude = data[offset : offset + 8]
        if _crc32(prelude) != prelude_crc:
            raise EventStreamError(f"Prelude CRC mismatch at offset {offset}")

        payload_start = offset + 12 + headers_len
        payload_end = offset + total_len - 4
        if payload_end < payload_start:
            raise EventStreamError(f"Negative payload length at offset {offset}")

        yield data[payload_start:payload_end]
        offset += total_len

    if offset != total:
        raise EventStreamError(f"Trailing {total - offset} bytes after last frame")


def _crc32(data: bytes) -> int:
    import zlib

    return zlib.crc32(data) & 0xFFFFFFFF
