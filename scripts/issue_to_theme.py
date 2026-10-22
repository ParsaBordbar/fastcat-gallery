#!/usr/bin/env python3
"""Turn a "Submit a theme" issue into themes/<code>/, checked with the same rules as a pull request.

    python3 scripts/issue_to_theme.py <github event json>

Run by .github/workflows/theme-issue.yml. On success it writes the theme folder and sets the step
output `code`; on failure it writes the reason to $RUNNER_TEMP/theme-error.md (posted back on the
issue) and exits 1. The issue body is untrusted: nothing from it reaches a shell, and the folder is
only written after the code passes CODE_RE.
"""
import json
import os
import re
import shutil
import sys
import urllib.request
from pathlib import Path

from build import CODE_RE, MAX_SCREENSHOT, SCREENSHOTS, THEMES, Invalid, validate

FIELDS = {"Code": "code", "Name": "name", "Description": "description", "Tags": "tags",
          "config.jsonc": "config", "ascii.txt": "logo", "Screenshot": "screenshot", "Rights": "rights"}
ATTACHMENT_RE = re.compile(r"https://(?:github\.com/user-attachments/assets/[A-Za-z0-9-]+"
                           r"|(?:private-)?user-images\.githubusercontent\.com/[^\s)\"'<>]+)")


def parse(body: str) -> dict:
    """Issue-form markdown ("### Label" then the answer) -> {field id: answer}."""
    out = {}
    parts = re.split(r"^### (.+?)[ \t]*$", body.replace("\r\n", "\n"), flags=re.M)
    for label, value in zip(parts[1::2], parts[2::2]):
        key = FIELDS.get(label.strip())
        if not key:
            continue
        value = value.strip("\n")
        if value.strip() == "_No response_":
            value = ""
        fence = re.fullmatch(r"\s*```[\w-]*\n(.*?)\n?```\s*", value, re.S)
        out[key] = fence.group(1) if fence else value.strip()
    return out


def fetch_screenshot(text: str) -> tuple[str, bytes] | None:
    m = ATTACHMENT_RE.search(text or "")
    if not m:
        return None
    req = urllib.request.Request(m.group(0), headers={"User-Agent": "fastcat-gallery-bot"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read(MAX_SCREENSHOT + 1)
    except OSError as e:
        raise Invalid(f"couldn't download the screenshot ({e})") from None
    if len(data) > MAX_SCREENSHOT:
        raise Invalid(f"the screenshot is larger than {MAX_SCREENSHOT // 1024} KB")
    for name, magic in SCREENSHOTS.items():
        if data.startswith(magic):
            return name, data
    raise Invalid("the screenshot must be a png or jpg")


def build_theme(issue: dict) -> str:
    f = parse(issue.get("body") or "")
    code = f.get("code", "").strip().lower()
    if not CODE_RE.match(code):
        raise Invalid(f"code {code!r} must be 2-32 chars of a-z, 0-9 and '-' (not starting or ending with '-')")
    if (THEMES / code).exists():
        raise Invalid(f"the code {code!r} is taken, pick another one")
    if "[x]" not in f.get("rights", "").lower():
        raise Invalid("please tick the rights checkbox")
    if not f.get("config", "").strip():
        raise Invalid("config.jsonc is empty")
    author = issue["user"]["login"]
    meta = {"name": f.get("name", "").strip(), "author": author, "description": f.get("description", "").strip(),
            "tags": [t.strip().lstrip("#") for t in f.get("tags", "").split(",") if t.strip()],
            "link": f"https://github.com/{author}"}
    shot = fetch_screenshot(f.get("screenshot", ""))

    folder = THEMES / code
    folder.mkdir(parents=True)
    try:
        (folder / "theme.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (folder / "config.jsonc").write_text(f["config"].rstrip() + "\n", encoding="utf-8")
        if f.get("logo", "").strip():
            (folder / "ascii.txt").write_text(f["logo"].rstrip("\n") + "\n", encoding="utf-8")
        if shot:
            (folder / shot[0]).write_bytes(shot[1])
        validate(folder)
    except BaseException:
        shutil.rmtree(folder)
        raise
    return code


def main() -> int:
    event = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    try:
        code = build_theme(event["issue"])
    except Invalid as e:
        msg = f"Couldn't add this theme yet:\n\n> {e}\n\nEdit the issue to fix it and I'll try again."
        Path(os.environ.get("RUNNER_TEMP", "."), "theme-error.md").write_text(msg, encoding="utf-8")
        print("✗", e, file=sys.stderr)
        return 1
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a", encoding="utf-8") as out:
        out.write(f"code={code}\n")
    print(f"✓ themes/{code}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
