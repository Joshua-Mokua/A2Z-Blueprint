#!/usr/bin/env python3
"""Show the bytes + decoded char around the suspicious 0x9d in pipeline_settings.json."""
import os
p = os.path.join("data", "pipeline_settings.json")
raw = open(p, "rb").read()
i = raw.find(b"\x9d")
print(f"file size: {len(raw)} bytes")
print(f"first 0x9d at byte: {i}")
if i >= 0:
    window = raw[max(0, i-30):i+30]
    print(f"raw bytes around it: {window!r}")
    # what utf-8 char does 0x9d participate in?
    # 0x9d alone is a continuation byte; show the full decoded context
    try:
        ctx = raw[max(0,i-30):i+30].decode("utf-8", errors="replace")
        print(f"utf-8 decoded (errors=replace): {ctx!r}")
    except Exception as e:
        print(f"decode note: {e}")
    # count all high bytes
    highs = sum(1 for b in raw if b >= 0x80)
    print(f"total non-ASCII bytes in file: {highs}")
    # Is the whole file valid utf-8?
    try:
        raw.decode("utf-8")
        print("WHOLE FILE: valid UTF-8 (the 0x9d is part of a valid multibyte char)")
    except Exception as e:
        print(f"WHOLE FILE: NOT valid UTF-8 -> {e}")
