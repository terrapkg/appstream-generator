FROM ghcr.io/terrapkg/builder:frawhide AS base

RUN dnf install -y \
    libappstream-glib-builder \
    gdk-pixbuf2 \
    rsvg-pixbuf-loader \
    python3 \
    uv \
    git-core \
    appstream \
    terra-appstream-helper

FROM base AS runtime

ADD . /app
WORKDIR /app
RUN uv sync --locked

CMD ["uv", "run", "main.py"]
