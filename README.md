# Nepal Acts — Image Generator

Paste a [nepalacts.com](https://nepalacts.com) post URL and get two social images
(English + Nepali headline) bundled in a ZIP.

- Fetches the headline (both languages) and featured photo from the site's API
- Scales the photo to fill a 1926 × 2400 canvas
- Adds the `#181D21` bottom gradient, the logo, and the headline
- English uses **Raleway ExtraBold**, Nepali uses **Mukta ExtraBold**
- Proper Devanagari shaping via **Raqm** (HarfBuzz)

## Run locally

```bash
pip install -r requirements.txt   # plus libraqm + librsvg system libs (see Dockerfile)
python3 app.py
```

Open **http://127.0.0.1:5050**

> Note: for correct Nepali rendering, Pillow must be built against `libraqm`.
> The Docker image does this automatically.

### Command line

```bash
python3 generate.py https://nepalacts.com/voices/birgunj-mayor-singh-arrested
```

Images are written to `output/`, named after the headline.

## Deploy to Render (free)

This repo is Render-ready (`Dockerfile` + `render.yaml`).

1. Push this repo to GitHub.
2. Go to [render.com](https://render.com) → **New → Web Service**.
3. Connect this GitHub repo. Render detects the `Dockerfile` automatically.
4. Pick the **Free** plan → **Create Web Service**.
5. After the build, you get a public URL like `https://nepalacts-generator.onrender.com`.

Every `git push` to the main branch auto-redeploys.

> Free instances sleep after ~15 min idle and take ~30 s to wake on the next request.
