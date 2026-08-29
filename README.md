# ShipReel

**Every PR ships with a reel.** ShipReel records a demo video of your app on every pull
request — and on the base branch, so you get **before/after** — then posts it as a sticky PR
comment. Review becomes watching a 30-second video instead of reading diffs or chasing Looms.

Inspired by *Feature-Rec* (YC × Anthropic × QRT × HF hackathon): AI agents made shipping 5×
faster, and product review is the step that never scaled. ShipReel is the solo-dev / small-team
version: the reviewer is you, the review surface is the PR, and the review unit is the video.

## How it works

```
PR opened/updated
   │
   ├─ run the repo's own walkthrough script on the PR head   → after.webm
   ├─ run it again on the base branch (head's harness)       → before.webm   (optional)
   ├─ ffmpeg: webm → mp4 (+ before/after side-by-side mp4, + gif previews)
   ├─ publish to a rolling `shipreel-videos` release in YOUR repo (per-PR assets, clobbered)
   └─ upsert a sticky PR comment with the video links
```

The walkthrough script **is** the demo script: when the UI changes you update the script (you
already do — it's also your e2e test), and the video can never drift from the product.

## Plug into any repo (2 steps)

**1. Add a walkthrough script** that drives a real browser through your app, drops `.webm`
recordings into `e2e/videos/`, and exits non-zero if any screen raised. Any framework works
(Playwright recommended — it records video natively). Reference implementation:
`mission-control`'s `e2e/test_demo_walkthrough.py` (Streamlit app, fixture-seeded, discovers
views dynamically).

**2. Add the caller workflow** `.github/workflows/shipreel.yml`:

```yaml
name: PR demo video
on:
  pull_request:
  workflow_dispatch:

permissions:
  contents: write       # publish videos to the rolling release
  pull-requests: write  # post/refresh the PR comment

jobs:
  shipreel:
    uses: Sharper8/shipreel/.github/workflows/shipreel.yml@main
    with:
      setup-command: pip install -r requirements.txt playwright && playwright install --with-deps chromium
      walkthrough-command: python -m pytest e2e/ -q
```

### Inputs

| Input | Default | Meaning |
| --- | --- | --- |
| `setup-command` | *(required)* | Install app deps + walkthrough deps |
| `walkthrough-command` | *(required)* | Runs the walkthrough; `.webm` → `video-dir`, non-zero exit on failure |
| `video-dir` | `e2e/videos` | Where the walkthrough drops recordings |
| `before-after` | `true` | Also record on the base branch; post before/after + side-by-side |
| `release-tag` | `shipreel-videos` | Rolling release hosting the videos |
| `python-version` | `3.11` | For setup-python (harmless for non-Python apps) |

## Design decisions & limitations

- **Deterministic over agentic.** A scripted browser run is reproducible, CI-friendly, and has no
  cursor wobble to smooth out in post. (Agentic capture — e.g. Demosmith — exists for marketing
  gloss; ShipReel is the per-PR engineering loop.)
- **Fixtures, not production data.** CI has no access to your real data sources. Seed the app
  with deterministic fixture data in the walkthrough so videos look real (see mission-control's
  `e2e/fixtures/`).
- **Private repos: videos are one click away, not inline.** GitHub only inline-plays videos
  uploaded through its own attachment pipeline, which CI tokens can't use; release assets
  force-download. For true in-browser play, host on a public URL (e.g. Cloudflare R2) — planned
  as an optional `hosting: r2` input. Trade-off: your app UI on a public URL.
- **A broken base never blocks a PR.** The before-recording is `continue-on-error`; only the
  head walkthrough gates the check.
- **Failure is self-documenting.** On failure you still get the partial recording + a
  `FAILURE-<screen>.png` screenshot in the run artifacts.

## Status

v0 — dogfooded on `Sharper8/mission-control` (see PR #6 thread for the full POC history:
the pipeline caught 3 real bugs before its first merge).
