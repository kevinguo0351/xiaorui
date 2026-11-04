"""Doubao v3 binary framing; no credentials, I/O, or audio persistence."""
import gzip
import json
import struct
import zlib

MAX_FRAME = 1_000_000


def encode_request(payload: bytes, *, audio: bool = False, final: bool = False) -> bytes:
    compressed = gzip.compress(payload)
    return bytes((0x11, (0x20 if audio else 0x10) | (2 if final else 0),
                  0x01 if audio else 0x11, 0)) + struct.pack('>I', len(compressed)) + compressed


def decode_response(frame: bytes) -> tuple[dict, bool]:
    if len(frame) < 8 or len(frame) > MAX_FRAME or frame[0] >> 4 != 1:
        raise ValueError('Invalid speech frame')
    offset = (frame[0] & 15) * 4
    kind, flags = frame[1] >> 4, frame[1] & 15
    serialization, compression = frame[2] >> 4, frame[2] & 15
    if offset < 4 or kind not in (9, 15) or serialization != 1 or compression not in (0, 1):
        raise ValueError('Unsupported speech frame')
    if flags & 1:
        offset += 4
    if kind == 15:
        raise ValueError('Speech provider rejected audio')
    if offset + 4 > len(frame):
        raise ValueError('Truncated speech frame')
    size = struct.unpack_from('>I', frame, offset)[0]
    body = frame[offset + 4:]
    if size != len(body):
        raise ValueError('Invalid speech payload size')
    if compression:
        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
        body = decompressor.decompress(body, MAX_FRAME + 1)
        if len(body) > MAX_FRAME or not decompressor.eof:
            raise ValueError('Speech payload too large or incomplete')
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError('Invalid speech payload')
    if parsed.get('code', 0) not in (0, 20000000):
        raise ValueError('Speech provider rejected audio')
    return parsed, bool(flags & 2)
