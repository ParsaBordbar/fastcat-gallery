# fastcat gallery

Community themes for [fastfetch](https://github.com/fastfetch-cli/fastfetch), browsable at
**https://parsabordbar.github.io/fastcat-gallery/** and installable from
[fastcat-tui](https://github.com/ParsaBordbar/fastcat-tui) by their code:

```sh
fastcat-tui get venom            # download it into your themes
fastcat-tui get venom --apply    # download and apply (your config is backed up first)
fastcat-tui gallery              # list everything in the gallery
```

In the TUI: **Community gallery** in the main menu, then search, pick a theme or type its code.
`fastcat-tui gallery <words>` and the site's search match the same way (every word, in the name,
author, description, tags or code), and searches can be linked: `?q=neon` or `?tag=cat`.

There is no server: the site is plain HTML/CSS/JS on GitHub Pages, rebuilt by a GitHub Action every
time a theme is merged.

## Submit a theme

You need a GitHub account. You don't need git. Pick whichever is easiest:

### 1. From fastcat-tui (easiest)

```sh
fastcat-tui share --name "Neon Cat"          # your current fastfetch config
fastcat-tui share Neon-Cat                    # or one of your saved themes
```

or in the TUI: **Community gallery → Share my config** (or *Share to the gallery* on one of your
themes). Your browser opens the submit form with everything filled in; tick the rights box and
submit. If your logo is too big for the link, fastcat-tui puts it on your clipboard and tells you
which box to paste it into.

### 2. The form

Open a [theme issue](../../issues/new?template=theme.yml), paste your `config.jsonc` and logo, and
optionally drag in a screenshot.

**Either way**, a bot checks the theme and opens a pull request for you (you're credited as the
author). If something's wrong it comments on your issue: edit the issue and it tries again.

### 3. A pull request

Add a folder `themes/<code>/`:

| file | what |
|---|---|
| `config.jsonc` | your fastfetch config, logo pointed at `~/.config/fastfetch/ascii.txt` |
| `ascii.txt` | your logo (fastfetch colour tags `$1`..`$9` work) |
| `theme.json` | name, author, description, tags, link |
| `screenshot.png` / `.jpg` | optional, up to 1 MB, shown on the site instead of the logo preview |

```json
{
  "name": "Neon Cat",
  "author": "your-github-name",
  "description": "One line about it.",
  "tags": ["cat", "neon"],
  "link": "https://github.com/you/where-it-came-from"
}
```

Check it with `python3 scripts/build.py --check` (Python 3.10+, nothing to install), then open the
pull request. You can do all of this on github.com: fork, *Add file → Upload files*, *Open pull request*.

### Rules

- The code (folder name) is what people type: 2-32 characters of `a-z`, `0-9` and `-`.
- Only `.jsonc`, `.json`, `.txt` and `.png` files plus the optional screenshot; 256 KB per file,
  1.5 MB per theme, no sub-folders.
- **Nothing that runs programs**: no `command` modules, no `general.preRun`, no `command-raw` logos.
  They would run on the user's machine, so the check rejects them and fastcat-tui refuses to install them.
- Text files are UTF-8 without terminal control characters. Strings in `config.jsonc` may use colour
  codes (`\u001b[31m`) but no other escape sequences.
- Logo paths have to stay inside the theme folder.
- Only submit themes you made or whose license lets you share them, and credit the source in `link`.

## Maintainers: one-time setup

1. Settings → Pages → Source: **GitHub Actions**.
2. Settings → Actions → General → Workflow permissions: tick **Allow GitHub Actions to create and
   approve pull requests** (the issue bot needs it).
3. Issues → Labels: create a label called **`theme`** (the form adds it; the bot only reacts to it).

Pull requests the bot opens don't re-run CI (GitHub doesn't trigger workflows from the bot's own
token), but the bot already ran the same check before opening them.

## Preview the site locally

```sh
python3 scripts/build.py && python3 -m http.server -d _site
```

## How fastcat-tui reads it

`_site/index.json` lists every theme with its files and their SHA-256. fastcat-tui downloads
`index.json`, then `themes/<code>/<file>` for each file, checks the hashes, and saves the theme to its
data folder, where it shows up in *Browse themes* under **Gallery**.

The seed themes `venom` and `persepolis` are by [ParsaBordbar](https://github.com/ParsaBordbar), from the
fastcat-tui originals. Their config layout follows [FastCat](https://github.com/m3tozz/FastCat)'s template
(MIT, see `themes/LICENSE-FastCat`).
