"""Bounded local authoring IO and the deliberately small published schema dialect."""
from __future__ import annotations
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any

LAB = Path(__file__).resolve().parents[1]
REPO = LAB.parent

class LabError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)

def require(ok: bool, code: str, message: str) -> None:
    if not ok:
        raise LabError(code, message)

def pairs(items: list) -> dict:
    result = {}
    for key, value in items:
        require(key not in result, "JSON_DUPLICATE", f"Duplicate key: {key}")
        result[key] = value
    return result

def loads(data: bytes | str) -> Any:
    require(len(data) <= 1_048_576, "JSON_SIZE", "JSON exceeds 1 MiB")
    try:
        return json.loads(data, object_pairs_hook=pairs,
                          parse_constant=lambda s: (_ for _ in ()).throw(LabError("JSON_NUMBER", s)))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as e:
        raise LabError("JSON_PARSE", str(e)) from e

def encode(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()

def relative(name: str) -> str:
    require(isinstance(name, str) and len(name) <= 240 and bool(name), "PATH", "Bounded relative path required")
    parts = name.split("/")
    require(all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", p) and ".." not in p for p in parts),
            "PATH", f"Unsafe path: {name}")
    require(not PurePosixPath(name).is_absolute(), "PATH", name)
    return name

def read_bytes(root: Path, name: str, limit: int = 64 * 1024 * 1024) -> bytes:
    """Descriptor-relative traversal. Reject every symlink component and nonregular leaf."""
    parts = relative(name).split("/")
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            before = os.fstat(leaf)
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= limit,
                    "FILE_BOUNDARY", f"Regular unlinked-to-other-name file <= {limit} bytes required: {name}")
            chunks, size = [], 0
            while True:
                chunk = os.read(leaf, min(65536, limit + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                require(size <= limit, "FILE_SIZE", name)
            after = os.fstat(leaf)
            require((before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                    (after.st_size, after.st_mtime_ns, after.st_ctime_ns) and size == after.st_size,
                    "FILE_CHANGED", name)
            return b"".join(chunks)
        finally:
            os.close(leaf)
    except OSError as e:
        raise LabError("FILE_BOUNDARY", f"Cannot read declared local file {name}: {e.strerror}") from e
    finally:
        os.close(fd)

def read_json(path: Path) -> Any:
    return loads(read_bytes(path.parent, path.name, 1_048_576))

def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode(value))

def validate(value: Any, schema: dict, at: str = "$", depth: int = 0) -> None:
    """Only the keywords emitted by schemas.py; never a general JSON Schema claim."""
    require(depth <= 48, "SCHEMA_DEPTH", at)
    if "oneOf" in schema:
        count = 0
        for variant in schema["oneOf"]:
            try:
                validate(value, variant, at, depth + 1)
                count += 1
            except LabError:
                pass
        require(count == 1, "SCHEMA", f"{at}: expected exactly one declared type")
        return
    if "const" in schema:
        require(type(value) is type(schema["const"]) and value == schema["const"], "SCHEMA", f"{at}: expected {schema['const']!r}")
    if "enum" in schema:
        require(any(type(value) is type(v) and value == v for v in schema["enum"]), "SCHEMA", f"{at}: unsupported value")
    kind = schema.get("type")
    types = {"object":dict, "array":list, "string":str, "integer":int, "boolean":bool, "null":type(None)}
    if kind == "number":
        require(type(value) in (int, float) and math.isfinite(value), "SCHEMA", f"{at}: finite number required")
    elif kind:
        require(type(value) is types[kind], "SCHEMA", f"{at}: expected {kind}")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        require(set(schema.get("required", [])) <= value.keys(), "SCHEMA", f"{at}: missing fields")
        if schema.get("additionalProperties") is False:
            require(value.keys() <= props.keys(), "SCHEMA", f"{at}: unknown fields {sorted(value.keys() - props.keys())}")
        for key, item in value.items():
            spec = props.get(key, schema.get("additionalProperties", {}))
            if isinstance(spec, dict):
                validate(item, spec, f"{at}.{key}", depth + 1)
        require(len(value) <= schema.get("maxProperties", 256), "SCHEMA", f"{at}: too many fields")
    if isinstance(value, list):
        require(schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 256), "SCHEMA", f"{at}: array bounds")
        if schema.get("uniqueItems"):
            require(len({encode(x) for x in value}) == len(value), "SCHEMA", f"{at}: duplicates")
        for i, item in enumerate(value):
            validate(item, schema.get("items", {}), f"{at}[{i}]", depth + 1)
    if isinstance(value, str):
        require(schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 8192), "SCHEMA", f"{at}: string bounds")
        require(not any(ord(c) < 32 and c not in "\n\t" for c in value), "SCHEMA", f"{at}: control character")
        if "pattern" in schema:
            require(re.fullmatch(schema["pattern"], value) is not None, "SCHEMA", f"{at}: invalid format")
    if type(value) in (int, float):
        require(math.isfinite(value) and schema.get("minimum", -1e15) <= value <= schema.get("maximum", 1e15),
                "SCHEMA", f"{at}: numeric bounds")
