"""Minimal reader/writer for the SNG container (Encore / YARG / Clone Hero).

Layout: b"SNGPKG" | u32 version | 16-byte xor mask
        | u64 metaLen | u64 metaCount | (i32 klen, key, i32 vlen, value)*
        | u64 indexLen | u64 fileCount | (u8 nlen, name, u64 size, u64 offset)*
        | u64 dataLen | data (each file XOR-masked: b ^ mask[i % 16] ^ (i & 0xFF))
"""
import hashlib
import os
import struct


import numpy as np


def _unmask(buf, mask):
    """XOR every byte with mask[i % 16] ^ (i & 0xFF). Symmetric: also used to mask."""
    a = np.frombuffer(buf, dtype=np.uint8)
    idx = np.arange(len(a), dtype=np.uint32)
    key = np.frombuffer(bytes(mask), dtype=np.uint8)[idx & 15] ^ (idx & 0xFF).astype(np.uint8)
    return (a ^ key).tobytes()


def read_sng(path, want=None):
    """Return (metadata dict, {filename: bytes}). `want`: optional set of filenames to extract."""
    with open(path, "rb") as f:
        if f.read(6) != b"SNGPKG":
            raise ValueError("not an SNG file")
        (version,) = struct.unpack("<I", f.read(4))
        mask = f.read(16)
        meta_len, meta_count = struct.unpack("<QQ", f.read(16))
        meta = {}
        for _ in range(meta_count):
            (kl,) = struct.unpack("<i", f.read(4)); k = f.read(kl).decode("utf-8", "replace")
            (vl,) = struct.unpack("<i", f.read(4)); v = f.read(vl).decode("utf-8", "replace")
            meta[k] = v
        idx_len, count = struct.unpack("<QQ", f.read(16))
        entries = []
        for _ in range(count):
            (nl,) = struct.unpack("<B", f.read(1)); name = f.read(nl).decode("utf-8", "replace")
            size, offset = struct.unpack("<QQ", f.read(16))
            entries.append((name, size, offset))
        files = {}
        for name, size, offset in entries:
            if want is not None and name not in want:
                continue
            f.seek(offset)
            files[name] = _unmask(f.read(size), mask)
        return meta, files, [e[0] for e in entries]


def extract(path, out_dir, want=None):
    meta, files, names = read_sng(path, want)
    os.makedirs(out_dir, exist_ok=True)
    for name, data in files.items():
        with open(os.path.join(out_dir, name), "wb") as f:
            f.write(data)
    with open(os.path.join(out_dir, "song.ini"), "w", encoding="utf-8") as f:
        f.write("[song]\n" + "".join(f"{k} = {v}\n" for k, v in meta.items()))
    return meta, names


def write_sng(out_path, metadata, files):
    """Write an SNG v1 package. metadata: {key: value}; files: {name: bytes}. Lengths include the
    count fields and offsets are absolute (checked against an Encore-made file)."""
    # deterministic mask (any 16 bytes are valid): identical input -> byte-identical .sng
    mask = hashlib.sha256(repr(sorted(metadata.items())).encode() + b"".join(files[n] for n in sorted(files))).digest()[:16]
    meta = b"".join(struct.pack("<i", len(k.encode())) + k.encode() + struct.pack("<i", len(str(v).encode())) + str(v).encode()
                    for k, v in metadata.items())
    meta_sec = struct.pack("<Q", len(metadata)) + meta
    names = list(files)
    idx_len = 8 + sum(1 + len(n.encode()) + 16 for n in names)
    data_start = 6 + 4 + 16 + 8 + len(meta_sec) + 8 + idx_len + 8
    idx, off = b"", data_start
    for n in names:
        idx += struct.pack("<B", len(n.encode())) + n.encode() + struct.pack("<QQ", len(files[n]), off)
        off += len(files[n])
    with open(out_path, "wb") as f:
        f.write(b"SNGPKG" + struct.pack("<I", 1) + mask)
        f.write(struct.pack("<Q", len(meta_sec)) + meta_sec)
        f.write(struct.pack("<QQ", idx_len, len(names)) + idx)
        f.write(struct.pack("<Q", sum(len(files[n]) for n in names)))
        for n in names:
            f.write(_unmask(files[n], mask))  # XOR masking is symmetric


def pack_folder(folder, out_path):
    """Song folder (song.ini + chart + audio) -> .sng. song.ini becomes the metadata block."""
    meta, files = {}, {}
    for name in sorted(os.listdir(folder)):
        p = os.path.join(folder, name)
        if name.lower() == "song.ini":
            for line in open(p, encoding="utf-8-sig"):
                if "=" in line and not line.strip().startswith("["):
                    k, v = line.split("=", 1)
                    meta[k.strip()] = v.strip()
        elif os.path.isfile(p):
            with open(p, "rb") as fh:
                files[name] = fh.read()
    write_sng(out_path, meta, files)

