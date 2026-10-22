#!/usr/bin/env python3
"""Validate every theme in themes/ and build the static site into _site/.

    python3 scripts/build.py            # validate + build _site/
    python3 scripts/build.py --check    # validate only (what CI runs on pull requests)

A theme is a folder themes/<code>/ holding theme.json, config.jsonc, the logo file(s) the
config points at and optionally screenshot.png / screenshot.jpg (shown on the site, not installed). <code> is what people type in fastcat-tui:  fastcat-tui get <code>
Standard library only, so it runs anywhere Python 3.10+ does.
"""
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
THEMES, SITE, OUT = ROOT / "themes", ROOT / "site", ROOT / "_site"

CODE_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$")
FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
ALLOWED_EXT = {".jsonc", ".json", ".txt", ".png"}
SCREENSHOTS = {"screenshot.png": b"\x89PNG\r\n\x1a\n", "screenshot.jpg": b"\xff\xd8\xff"}
MAX_FILE, MAX_SCREENSHOT, MAX_THEME = 256 * 1024, 1024 * 1024, 1536 * 1024
# A theme must never execute anything on the user's machine: no modules that run programs, no
# general.preRun, and every logo type except command-raw. fastcat-tui's gallery.py checks the same.
BLOCKED_MODULES = {"command"}
SAFE_LOGO_TYPES = {"auto", "builtin", "small", "file", "file-raw", "data", "data-raw", "sixel", "kitty",
                   "kitty-direct", "kitty-icat", "iterm", "chafa", "raw", "none"}
CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")   # tab and newline are fine
SGR_RE = re.compile(r"\x1b\[[0-9;]*m")                      # colour codes are fine in config strings
CONFIG_DIR_PREFIX = re.compile(r"^(~|\$HOME|\$\{HOME\})/\.config/fastfetch/")


# ---------------------------------------------------------------- jsonc
_TOKEN_RE = re.compile(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*.*?\*/', re.S)


def jsonc_loads(text: str):
    text = _TOKEN_RE.sub(lambda m: m.group(0) if m.group(0).startswith('"') else "", text)
    out, i = [], 0
    for m in re.finditer(r'"(?:\\.|[^"\\])*"|,(?=\s*[}\]])', text):
        out.append(text[i:m.start()])
        if m.group(0) != ",":
            out.append(m.group(0))
        i = m.end()
    out.append(text[i:])
    return json.loads("".join(out))


# ---------------------------------------------------------------- colours (for the web preview)
_BASIC = ["#000000", "#cd3131", "#0dbc79", "#e5e510", "#2472c8", "#bc3fbc", "#11a8cd", "#e5e5e5",
          "#666666", "#f14c4c", "#23d18b", "#f5f543", "#3b8eea", "#d670d6", "#29b8db", "#ffffff"]
_NAMED = {n: i for i, n in enumerate(["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"])}
_CUBE = (0, 95, 135, 175, 215, 255)


def _xterm(n: int) -> str:
    if n < 16:
        return _BASIC[n]
    if n < 232:
        n -= 16
        r, g, b = _CUBE[n // 36], _CUBE[(n // 6) % 6], _CUBE[n % 6]
    else:
        r = g = b = 8 + 10 * (n - 232)
    return f"#{r:02x}{g:02x}{b:02x}"


def css_color(spec) -> str | None:
    """fastfetch colour spec ("red", "38;5;208", "1;34", "#ff8800") -> CSS hex, None for default."""
    s = str(spec).strip().lower().replace("bright_", "light_")
    bright = s.startswith("light_")
    s = s.removeprefix("light_")
    if s in _NAMED:
        return _BASIC[_NAMED[s] + (8 if bright else 0)]
    if re.fullmatch(r"#?[0-9a-f]{6}", s):
        return "#" + s.lstrip("#")
    if re.fullmatch(r"[0-9;]+", s):
        p = [int(x) for x in s.split(";") if x]
        for i, v in enumerate(p):
            if v == 38 and p[i + 1:i + 2] == [5] and i + 2 < len(p):
                return _xterm(p[i + 2])
            if v == 38 and p[i + 1:i + 2] == [2] and i + 4 < len(p):
                return "#" + "".join(f"{min(c, 255):02x}" for c in p[i + 2:i + 5])
            if 30 <= v <= 37:
                return _BASIC[v - 30 + (8 if 1 in p else 0)]
            if 90 <= v <= 97:
                return _BASIC[v - 90 + 8]
    return None


# ---------------------------------------------------------------- validation
class Invalid(Exception):
    pass


def _key(d, name: str):
    """d[name] ignoring case, the way fastfetch reads config keys."""
    if not isinstance(d, dict):
        return None
    return next((v for k, v in d.items() if isinstance(k, str) and k.lower() == name), None)


def _strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for k, v in x.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)


def check_config(cfg) -> list:
    """Reject configs that make fastfetch run programs or print escapes other than colours. Returns the modules."""
    if not isinstance(cfg, dict):
        raise Invalid("config.jsonc must be an object")
    modules = _key(cfg, "modules") or []
    if not isinstance(modules, list):
        raise Invalid("config.jsonc: 'modules' must be a list")
    for m in modules:
        t = _key(m, "type") if isinstance(m, dict) else m
        if isinstance(t, str) and t.lower() in BLOCKED_MODULES:
            raise Invalid(f"config.jsonc: the '{t}' module runs programs and is not allowed")
    if _key(_key(cfg, "general"), "prerun") is not None:
        raise Invalid("config.jsonc: general.preRun runs programs and is not allowed")
    t = _key(_key(cfg, "logo"), "type")
    if t is not None and (not isinstance(t, str) or t.lower() not in SAFE_LOGO_TYPES):
        raise Invalid(f"config.jsonc: logo type {t!r} is not allowed (command-raw runs programs)")
    if any(CONTROL_RE.search(SGR_RE.sub("", s)) for s in _strings(cfg)):
        raise Invalid("config.jsonc: strings may use colour codes but no other escape sequences")
    return modules


def _logo_sources(cfg: dict) -> list[str]:
    lg = cfg.get("logo")
    if isinstance(lg, str):
        return [lg]
    if isinstance(lg, dict) and isinstance(lg.get("source"), str):
        if lg.get("type") in ("builtin", "small", "data", "data-raw", "none"):
            return []
        return [lg["source"]]
    return []


def _local_name(source: str) -> str | None:
    """File name inside the theme folder a logo source points at, or None for a built-in logo name."""
    s = CONFIG_DIR_PREFIX.sub("", source)
    if s == source and ("/" not in s and "." not in s):
        return None                      # a built-in logo like "arch"
    if "/" in s or "\\" in s or not FILE_RE.match(s):
        raise Invalid(f"logo source {source!r} must be ~/.config/fastfetch/<file> or a plain file name in the theme folder")
    return s


def validate(folder: Path) -> dict:
    code = folder.name
    if not CODE_RE.match(code):
        raise Invalid("folder name (the theme code) must be 2-32 chars of a-z, 0-9 and '-'")
    files, screenshot, total = [], None, 0
    for f in sorted(folder.iterdir()):
        if f.is_symlink() or not f.is_file():
            raise Invalid(f"{f.name}: only plain files, no folders or links")
        size = f.stat().st_size
        total += size
        if f.name in SCREENSHOTS:
            if screenshot:
                raise Invalid("only one screenshot (png or jpg)")
            if size > MAX_SCREENSHOT:
                raise Invalid(f"{f.name}: larger than {MAX_SCREENSHOT // 1024} KB")
            if not f.read_bytes().startswith(SCREENSHOTS[f.name]):
                raise Invalid(f"{f.name}: not a real {f.suffix[1:]} image")
            screenshot = f.name
            continue
        if not FILE_RE.match(f.name) or f.suffix.lower() not in ALLOWED_EXT:
            raise Invalid(f"{f.name}: allowed files are {', '.join(sorted(ALLOWED_EXT))} with simple names, "
                          "plus screenshot.png or screenshot.jpg")
        if size > MAX_FILE:
            raise Invalid(f"{f.name}: larger than {MAX_FILE // 1024} KB")
        if f.suffix.lower() != ".png":      # fastcat-tui refuses text it could not print safely
            try:
                text = f.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                raise Invalid(f"{f.name}: not UTF-8 text") from None
            if CONTROL_RE.search(text.replace("\r\n", "\n")):
                raise Invalid(f"{f.name}: contains terminal control characters")
        files.append(f.name)
    if total > MAX_THEME:
        raise Invalid(f"theme is larger than {MAX_THEME // 1024} KB in total")
    for need in ("theme.json", "config.jsonc"):
        if need not in files:
            raise Invalid(f"missing {need}")

    try:
        meta = json.loads((folder / "theme.json").read_text(encoding="utf-8"))
    except ValueError as e:
        raise Invalid(f"theme.json: {e}") from None
    if not isinstance(meta, dict):
        raise Invalid("theme.json must be an object")
    for key, limit in (("name", 40), ("author", 40)):
        if not isinstance(meta.get(key), str) or not meta[key].strip() or len(meta[key]) > limit:
            raise Invalid(f"theme.json: '{key}' is required (text, up to {limit} chars)")
    desc = meta.get("description", "")
    if not isinstance(desc, str) or len(desc) > 200:
        raise Invalid("theme.json: 'description' must be text, up to 200 chars")
    tags = meta.get("tags", [])
    if not isinstance(tags, list) or len(tags) > 6 or not all(isinstance(t, str) and 0 < len(t) <= 20 for t in tags):
        raise Invalid("theme.json: 'tags' must be a list of up to 6 short words")
    link = meta.get("link", "")
    if not isinstance(link, str) or (link and not link.startswith("https://")):
        raise Invalid("theme.json: 'link' must be an https:// URL")

    try:
        cfg = jsonc_loads((folder / "config.jsonc").read_text(encoding="utf-8"))
    except ValueError as e:
        raise Invalid(f"config.jsonc: {e}") from None
    modules = check_config(cfg)

    logo_text = None
    for src in _logo_sources(cfg):
        name = _local_name(src)
        if name is None:
            continue
        if name not in files:
            raise Invalid(f"config.jsonc points at {name}, which is not in the theme folder")
        if name.endswith(".txt"):
            logo_text = (folder / name).read_text(encoding="utf-8", errors="replace")

    lg = cfg.get("logo") if isinstance(cfg.get("logo"), dict) else {}
    lcolors = lg.get("color") if isinstance(lg.get("color"), dict) else {}
    key_colors = [css_color(m["keyColor"]) for m in modules
                  if isinstance(m, dict) and "keyColor" in m and m.get("type") != "break"]
    return {
        "code": code,
        "name": meta["name"].strip(),
        "author": meta["author"].strip(),
        "description": desc.strip(),
        "tags": [t.strip().lower() for t in tags],
        "link": link,
        "files": {f: hashlib.sha256((folder / f).read_bytes()).hexdigest() for f in files},
        "screenshot": screenshot,
        "logo": logo_text,
        "colors": {k: css_color(v) for k, v in lcolors.items() if str(k).isdigit()},
        "keyColors": [c for c in key_colors if c][:12],
        "lines": sum(1 for m in modules if (m.get("type") if isinstance(m, dict) else m) != "break"),
    }


# ---------------------------------------------------------------- main
def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    entries, errors = [], []
    for folder in sorted(p for p in THEMES.iterdir() if p.is_dir()):
        try:
            entries.append(validate(folder))
        except Invalid as e:
            errors.append(f"themes/{folder.name}: {e}")
        except Exception as e:              # a check that tripped over odd input: still report it, per theme
            errors.append(f"themes/{folder.name}: could not check it ({type(e).__name__}: {e})")
    for e in errors:
        print("✗", e, file=sys.stderr)
    if errors:
        return 1
    print(f"✓ {len(entries)} theme(s) valid")
    if check_only:
        return 0

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(SITE, OUT)
    for e in entries:
        dest = OUT / "themes" / e["code"]
        dest.mkdir(parents=True)
        for f in list(e["files"]) + ([e["screenshot"]] if e["screenshot"] else []):
            shutil.copy2(THEMES / e["code"] / f, dest / f)
    index = {"version": 1, "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "themes": entries}
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"✓ built {OUT.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
