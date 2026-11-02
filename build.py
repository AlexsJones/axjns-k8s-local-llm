#!/usr/bin/env python3
"""Build site/index.html from README.md. Tab blocks in the markdown
(<!-- tab:cpu intel --> ... <!-- /tab -->) become hardware-switchable divs."""
import re, markdown, html, pathlib, shutil
src = pathlib.Path("README.md").read_text()
# Screenshots live in img/ (what README.md references, so they render on GitHub).
# Mirror them into site/img/: this page uses them, and axjns.dev fetches
# raw .../main/site/img/<name>.png and vendors site/img/*.png.
pathlib.Path("site/img").mkdir(parents=True, exist_ok=True)
for old_png in pathlib.Path("site/img").glob("*.png"):
    if not pathlib.Path("img", old_png.name).exists():
        old_png.unlink()
for png in sorted(pathlib.Path("img").glob("*.png")):
    shutil.copy2(png, pathlib.Path("site/img", png.name))
missing = [m for m in re.findall(r"\]\((img/[^)]+)\)", src) if not pathlib.Path(m).exists()]
if missing:
    raise SystemExit(f"README references missing images: {missing}")
src = re.sub(r"<!-- tab:([a-z ]+) -->", lambda m: f'<div data-hw="{m.group(1)}" markdown="1">', src)
src = src.replace("<!-- /tab -->", "</div>")
picker = '''<div class="hw-picker" role="tablist" aria-label="Your hardware">
<div class="label">Your hardware (every hardware-specific step below follows this choice)</div>
<div class="tabs">
<button data-select="cpu" role="tab">CPU only <span class="badge tested">tested</span></button>
<button data-select="intel" role="tab">Intel Arc <span class="badge tested">tested</span></button>
<button data-select="nvidia" role="tab">NVIDIA <span class="badge tested">tested</span></button>
<button data-select="amd" role="tab">AMD <span class="badge tested">tested</span></button>
</div></div>'''
src = src.replace("<!-- picker -->", picker)
src = src.replace("> **Pick your hardware once** and every hardware-specific step on this page switches to match. On GitHub you'll just see all four versions one after another.\n",
                  "> **Pick your hardware once** below and every hardware-specific step on this page switches to match. Your choice is remembered.\n")
md = markdown.Markdown(extensions=["fenced_code", "tables", "md_in_html", "toc"])
body = md.convert(src)
body = re.sub(r'(<h2 id="spotted-something-wrong-tell-me">.*)$', r'<section class="feedback">\1</section>', body, flags=re.S)
body = re.sub(r'(<img alt="[^"]*" src="(img/[^"]+)" />)', r'<a class="shot" href="\2">\1</a>', body)
body = body.replace('<pre><code class="language-text">', '<pre class="out"><code class="language-text">')
title = "From zero to serving a model on Kubernetes, on your own machine"
page = f'''<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · Alex Jones</title>
<meta name="description" content="Run an LLM on Kubernetes on your own laptop or desktop: kind, llmfit, Ollama, GPUs (Intel, NVIDIA, AMD) and debugging with k8sgpt, with real output.">
<link rel="stylesheet" href="style.css">
</head><body class="hw-cpu"><main>
{body}
</main><script src="hw.js"></script></body></html>
'''
pathlib.Path("site").mkdir(exist_ok=True)
pathlib.Path("site/index.html").write_text(page)
print("wrote site/index.html", len(page))
