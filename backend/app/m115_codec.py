from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass


G_KTS = [
    240,
    229,
    105,
    174,
    191,
    220,
    191,
    138,
    26,
    69,
    232,
    190,
    125,
    166,
    115,
    184,
    222,
    143,
    231,
    196,
    69,
    218,
    134,
    196,
    155,
    100,
    139,
    20,
    106,
    180,
    241,
    170,
    56,
    1,
    53,
    158,
    38,
    105,
    44,
    134,
    0,
    107,
    79,
    165,
    54,
    52,
    98,
    166,
    42,
    150,
    104,
    24,
    242,
    74,
    253,
    189,
    107,
    151,
    143,
    77,
    143,
    137,
    19,
    183,
    108,
    142,
    147,
    237,
    14,
    13,
    72,
    62,
    215,
    47,
    136,
    216,
    254,
    254,
    126,
    134,
    80,
    149,
    79,
    209,
    235,
    131,
    38,
    52,
    219,
    102,
    123,
    156,
    126,
    157,
    122,
    129,
    50,
    234,
    182,
    51,
    222,
    58,
    169,
    89,
    52,
    102,
    59,
    170,
    186,
    129,
    96,
    72,
    185,
    213,
    129,
    156,
    248,
    108,
    132,
    119,
    255,
    84,
    120,
    38,
    95,
    190,
    232,
    30,
    54,
    159,
    52,
    128,
    92,
    69,
    44,
    155,
    118,
    213,
    27,
    143,
    204,
    195,
    184,
    245,
]
G_KEY_S = bytes([41, 35, 33, 94])
G_KEY_L = bytes([120, 6, 173, 76, 51, 134, 93, 24, 76, 1, 63, 70])
RSA_MODULE = int(
    "8686980c0f5a24c4b9d43020cd2c22703ff3f450756529058b1cf88f09b8602136477198a6e2683149659bd122c33592fdb5ad47944ad1ea4d36c6b172aad6338c3bb6ac6227502d010993ac967d1aef00f0c8e038de2e4d3bc2ec368af2e9f10a6f1eda4f7262f136420c07c331b871bf139f74f3010e3c4fe57df3afb71683",
    16,
)
RSA_EXPONENT = 0x10001
RSA_KEY_SIZE = 128
RSA_PLAIN_BLOCK_SIZE = RSA_KEY_SIZE - 11


@dataclass(frozen=True)
class Encoded115Payload:
    data: str
    key: bytes
    timestamp: int


def _md5_hex(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()


def _int_to_bytes(value: int, size: int | None = None) -> bytes:
    length = max(1, (value.bit_length() + 7) // 8)
    raw = value.to_bytes(length, "big")
    if size is not None:
        return raw.rjust(size, b"\x00")
    return raw


def _pkcs1_pad(block: bytes) -> bytes:
    if RSA_KEY_SIZE < len(block) + 11:
        raise ValueError("115 RSA block is too large")
    padded = bytearray(RSA_KEY_SIZE)
    offset = RSA_KEY_SIZE
    for value in reversed(block):
        offset -= 1
        padded[offset] = value
    offset -= 1
    padded[offset] = 0
    while offset > 2:
        offset -= 1
        padded[offset] = 0xFF
    offset -= 1
    padded[offset] = 2
    offset -= 1
    padded[offset] = 0
    return bytes(padded)


def _pkcs1_unpad(value: int) -> bytes:
    padded = _int_to_bytes(value)
    start = 1 if padded and padded[0] == 0 else 0
    if len(padded) > start and padded[start] in (1, 2):
        start += 1
    try:
        separator = padded.index(0, start)
    except ValueError as exc:
        raise ValueError("115 RSA response padding is invalid") from exc
    return padded[separator + 1 :]


def _rsa_encrypt_block(block: bytes) -> bytes:
    padded = _pkcs1_pad(block)
    value = pow(int.from_bytes(padded, "big"), RSA_EXPONENT, RSA_MODULE)
    return _int_to_bytes(value, RSA_KEY_SIZE)


def _rsa_decrypt_block(block: bytes) -> bytes:
    value = pow(int.from_bytes(block, "big"), RSA_EXPONENT, RSA_MODULE)
    return _pkcs1_unpad(value)


def _get_key(length: int, key: bytes | None) -> bytes:
    if key:
        return bytes(
            (((key[i] + G_KTS[length * i]) & 0xFF) ^ G_KTS[length * (length - 1 - i)])
            for i in range(length)
        )
    return G_KEY_L if length == 12 else G_KEY_S


def _xor115(data: bytes, key: bytes) -> bytes:
    mod4 = len(data) % 4
    result = bytearray(len(data))
    for index in range(mod4):
        result[index] = data[index] ^ key[index % len(key)]
    for index in range(mod4, len(data)):
        result[index] = data[index] ^ key[(index - mod4) % len(key)]
    return bytes(result)


def m115_sym_encode(data: bytes, key1: bytes) -> bytes:
    first = _xor115(data, _get_key(4, key1))
    return _xor115(first[::-1], _get_key(12, None))


def m115_sym_decode(data: bytes, key1: bytes, key2: bytes) -> bytes:
    first = _xor115(data, _get_key(12, key2))
    return _xor115(first[::-1], _get_key(4, key1))


def encode_115_payload(payload: str, timestamp: int | None = None) -> Encoded115Payload:
    actual_timestamp = timestamp or int(time.time())
    key = _md5_hex(f"!@###@#{actual_timestamp}DFDR@#@#").encode("latin1")
    encoded = m115_sym_encode(payload.encode("latin1"), key)
    input_data = key[:16] + encoded
    chunks = [
        _rsa_encrypt_block(input_data[offset : offset + RSA_PLAIN_BLOCK_SIZE])
        for offset in range(0, len(input_data), RSA_PLAIN_BLOCK_SIZE)
    ]
    return Encoded115Payload(
        data=base64.b64encode(b"".join(chunks)).decode("ascii"),
        key=key,
        timestamp=actual_timestamp,
    )


def decode_115_payload(base64_payload: str, key: bytes) -> str:
    input_data = base64.b64decode(base64_payload)
    chunks = [
        _rsa_decrypt_block(input_data[offset : offset + RSA_KEY_SIZE])
        for offset in range(0, len(input_data), RSA_KEY_SIZE)
    ]
    decoded = b"".join(chunks)
    seed = decoded[:16]
    body = decoded[16:]
    output = m115_sym_decode(body, key, seed)
    try:
        utf8 = output.decode("utf-8")
        json.loads(utf8)
        return utf8
    except (UnicodeDecodeError, json.JSONDecodeError):
        return output.decode("latin1")
