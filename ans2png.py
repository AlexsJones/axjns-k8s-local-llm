#!/usr/bin/env python3
"""Render captured ANSI terminal output (tmux capture-pane -e, or plain command
output) to a PNG. Minimal SGR->HTML conversion, then headless Chrome screenshots
it. The text is not edited; only colours are interpreted."""
import sys, re, html, subprocess, tempfile
from PIL import Image
src, out = sys.argv[1], sys.argv[2]
title = sys.argv[3] if len(sys.argv) > 3 else ""
data = open(src, encoding="utf-8", errors="replace").read().rstrip("\n")
BASE = ["#1b1e26","#e06c75","#98c379","#e5c07b","#61afef","#c678dd","#56b6c2","#dcdfe4",
        "#5c6370","#ff7b86","#b5e890","#ffd68a","#7cc4ff","#e29dff","#7fd8e3","#ffffff"]
def x256(n):
    if n < 16: return BASE[n]
    if n < 232:
        n -= 16; c = [0,95,135,175,215,255]
        return "#%02x%02x%02x" % (c[n//36], c[(n//6)%6], c[n%6])
    v = 8 + (n-232)*10; return "#%02x%02x%02x" % (v,v,v)
fg = bg = None; bold = False; outp = []
tok = re.compile(r"\x1b\[([0-9;?]*)([A-Za-z])|([^\x1b]+)|\x1b.")
for m in tok.finditer(data):
    if m.group(3) is not None:
        st = []
        if fg: st.append("color:"+fg)
        if bg: st.append("background:"+bg)
        if bold: st.append("font-weight:bold")
        t = html.escape(m.group(3))
        outp.append("<span style='%s'>%s</span>" % (";".join(st), t) if st else t)
        continue
    if m.group(2) != "m": continue
    ps = [int(p) if p.isdigit() else 0 for p in (m.group(1) or "0").split(";")]
    i = 0
    while i < len(ps):
        p = ps[i]
        if p == 0: fg = bg = None; bold = False
        elif p == 1: bold = True
        elif p == 22: bold = False
        elif 30 <= p <= 37: fg = BASE[p-30]
        elif 90 <= p <= 97: fg = BASE[p-90+8]
        elif 40 <= p <= 47: bg = BASE[p-40]
        elif 100 <= p <= 107: bg = BASE[p-100+8]
        elif p == 39: fg = None
        elif p == 49: bg = None
        elif p in (38, 48) and i+1 < len(ps):
            if ps[i+1] == 5 and i+2 < len(ps): c = x256(ps[i+2]); i += 2
            elif ps[i+1] == 2 and i+4 < len(ps): c = "#%02x%02x%02x" % tuple(ps[i+2:i+5]); i += 4
            else: c = None
            if p == 38: fg = c
            else: bg = c
        i += 1
body = "".join(outp)
plain_lines = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", data).split("\n")
width = max(len(l) for l in plain_lines); nlines = len(plain_lines)
page = f"""<html><body style='margin:0;background:#0f1115'>
<div style='display:inline-block;margin:16px;background:#1b1e26;border-radius:10px;overflow:hidden'>
<div style='padding:8px 12px;background:#262a33;color:#9a978e;font:12px sans-serif'>
<span style='color:#ff5f56'>&#9679;</span> <span style='color:#ffbd2e'>&#9679;</span> <span style='color:#27c93f'>&#9679;</span>&nbsp;&nbsp;{html.escape(title)}</div>
<pre style='margin:0;padding:12px 16px;color:#dcdfe4;font-family:"DejaVu Sans Mono",monospace;font-size:13px;line-height:1.3;white-space:pre'>{body}</pre></div></body></html>"""
tmp = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False); tmp.write(page); tmp.close()
w = int(width * 8.2) + 120; h = int(nlines * 17.2) + 120
subprocess.run(["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                "--force-device-scale-factor=1", f"--screenshot={out}", f"--window-size={w},{h}", "file://" + tmp.name],
               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
im = Image.open(out).convert("RGB"); px = im.load(); bgc = px[2, 2]
far = lambda a: sum(abs(a[i]-bgc[i]) for i in range(3)) > 12
xs = [x for x in range(im.width) if any(far(px[x, y]) for y in range(0, im.height, 3))]
ys = [y for y in range(im.height) if any(far(px[x, y]) for x in range(0, im.width, 3))]
if xs and ys: im = im.crop((max(xs[0]-10,0), max(ys[0]-10,0), min(xs[-1]+10, im.width), min(ys[-1]+10, im.height)))
im.save(out); print(out, im.size)
