FROM fedora:42 AS base

RUN --mount=type=cache,target=/var/cache/ dnf install -y \
    --setopt=install_weak_deps=False \
    libappstream-glib-builder \
    python3 \
    uv \
    git

FROM base AS runtime

ADD . /app
WORKDIR /app
RUN uv sync --locked

CMD ["uv", "run", "main.py"]