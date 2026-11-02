# Contributing

Thanks for helping make this guide better. The most useful contributions are reports from hardware I haven't tested on.

## Ground rules

- **Only show output you actually saw.** Every command and output block in the guide was run for real. If you change a command, run it and paste what came back. Screenshots must be real too.
- **Say what you ran it on.** Include your hardware (CPU, GPU, gfx target or compute capability), OS and kernel, Docker version, kind version and node image, and the Ollama image tag.
- **Keep versions current.** If you bump a version (kind, Kubernetes node image, Ollama, device plugins, llmfit, k8sgpt, k9s), update the version table at the end of `README.md` and the "Versions verified on" line.
- **Keep the tab markers intact.** Hardware-specific blocks are wrapped in `<!-- tab:cpu intel nvidia amd -->` ... `<!-- /tab -->`. The site build turns these into the hardware picker.

## Making a change

1. Edit `README.md` (it is the source for the website page).
2. If you add a screenshot, put the PNG in `img/` and reference it as `img/<name>.png`. `python3 build.py` copies it into `site/img/`, which axjns.dev reads from; commit both.
3. Build the static page: `python3 build.py` (needs `pip install markdown`), then open `site/index.html`.
4. Open a pull request using the template.

## Reporting a problem

Open an issue, or use the contact form at https://axjns.dev/#contact. Include the step, the command, and the full error output.
