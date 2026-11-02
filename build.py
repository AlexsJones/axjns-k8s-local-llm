#!/usr/bin/env python3
"""Build site/index.html from README.md. Tab blocks in the markdown
(<!-- tab:cpu intel --> ... <!-- /tab -->) become hardware-switchable divs."""
import re, markdown, html, pathlib
src = pathlib.Path("README.md").read_text()
src = re.sub(r"<!-- tab:([a-z ]+) -->", lambda m: f'<div data-hw="{m.group(1)}" markdown="1">', src)
src = src.replace("<!-- /tab -->", "</div>")
picker = '''<div class="hw-picker" role="tablist" aria-label="Your hardware">
<div class="label">Your hardware (every hardware-specific step below follows this choice)</div>
<div class="tabs">
<button data-select="cpu" role="tab">CPU only <span class="badge tested">tested</span></button>
<button data-select="intel" role="tab">Intel Arc <span class="badge tested">tested</span></button>
<button data-select="nvidia" role="tab">NVIDIA</button>
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
