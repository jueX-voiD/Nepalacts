FROM python:3.12-slim

# System libraries:
#  - libraqm-dev pulls in HarfBuzz + FriBiDi so Pillow can shape complex
#    scripts (Devanagari conjuncts / reordered vowel signs) correctly.
#  - build-essential + the -dev libs let us compile Pillow from source.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libraqm-dev \
        libfreetype6-dev \
        libjpeg-dev \
        zlib1g-dev \
        libpng-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# Build Pillow from source so it links against libraqm (Raqm layout engine).
RUN pip install --no-cache-dir --no-binary Pillow -r requirements.txt

COPY . .

ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT} --workers 2 --timeout 120"]
