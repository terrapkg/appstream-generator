# libfyaml is pinned to what asgen upstream CI uses; 0.9.6 headers break C++ builds
ARG LIBFYAML_VERSION=v0.9.4
ARG APPSTREAM_VERSION=v1.2.1
ARG ASGEN_VERSION=v1.0.0

# appstream-generator 1.0 needs appstream >= 1.2 and libfyaml >= 0.9.2,
# neither of which Fedora ships yet, so build the whole stack into /usr/local.
FROM ghcr.io/terrapkg/builder:frawhide AS asgen-build
ARG LIBFYAML_VERSION
ARG APPSTREAM_VERSION
ARG ASGEN_VERSION

RUN --mount=type=cache,target=/var/cache/libdnf5,sharing=locked \
    dnf install -y --setopt=keepcache=True \
    git-core gcc gcc-c++ meson ninja-build cmake gperf \
    glib2-devel libxml2-devel libxmlb-devel libcurl-devel libzstd-devel \
    cairo-devel fontconfig-devel freetype-devel pango-devel vips-devel vips-jxl itstool \
    lmdb-devel libarchive-devel tbb-devel libicu-devel json-devel inja-devel \
    catch-devel libxslt docbook5-style-xsl

ENV PKG_CONFIG_PATH=/usr/local/lib64/pkgconfig:/usr/local/lib/pkgconfig
WORKDIR /src

RUN git clone --depth 1 -b ${LIBFYAML_VERSION} https://github.com/pantoniou/libfyaml \
    && cmake -S libfyaml -B libfyaml/build -GNinja -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/usr/local -DCMAKE_INSTALL_LIBDIR=lib64 \
        -DENABLE_LIBCLANG=OFF -DBUILD_TESTING=OFF \
    && cmake --build libfyaml/build && cmake --install libfyaml/build

RUN git clone --depth 1 -b ${APPSTREAM_VERSION} https://github.com/ximion/appstream \
    && meson setup appstream/build appstream --prefix=/usr/local --buildtype=release \
        -Dcompose=true -Dstemming=false -Dsystemd=false -Dgir=false -Dvapi=false \
        -Dblake3-support=false -Ddocs=false -Dapidocs=false -Dinstall-docs=false -Dman=false \
        -Dbash-completion=false -Ddisplay-detection=none \
    && meson install -C appstream/build

RUN echo /usr/local/lib64 > /etc/ld.so.conf.d/usr-local.conf && ldconfig

RUN git clone --depth 1 -b ${ASGEN_VERSION} https://github.com/ximion/appstream-generator \
    && meson setup asgen/build appstream-generator --prefix=/usr/local --buildtype=release \
        -Dbackward=false \
    && meson install -C asgen/build

# asgen only finds icon themes in packages, so the stock icons (Adwaita, Breeze)
# come from Fedora's theme RPMs, served as a base suite (ICON_THEMES_DIR).
FROM ghcr.io/terrapkg/builder:frawhide AS icon-themes
RUN --mount=type=cache,target=/var/cache/libdnf5,sharing=locked \
    dnf download --setopt=keepcache=True --destdir /icon-themes \
    hicolor-icon-theme adwaita-icon-theme adwaita-icon-theme-legacy breeze-icon-theme \
    && createrepo_c /icon-themes

FROM ghcr.io/terrapkg/builder:frawhide AS base

RUN --mount=type=cache,target=/var/cache/libdnf5,sharing=locked \
    dnf install -y --setopt=keepcache=True \
    glib2 libxml2 libxmlb libcurl libzstd cairo fontconfig freetype pango vips \
    vips-jxl librsvg2 lmdb-libs libarchive tbb libicu \
    optipng \
    python3.13 \
    uv

COPY --from=asgen-build /usr/local /usr/local
COPY --from=icon-themes /icon-themes /usr/share/terra-appstream/icon-themes
ENV ICON_THEMES_DIR=/usr/share/terra-appstream/icon-themes
RUN echo /usr/local/lib64 > /etc/ld.so.conf.d/usr-local.conf && ldconfig \
    && appstream-generator --version

FROM base AS runtime

ADD . /app
WORKDIR /app
RUN uv sync --locked

CMD ["uv", "run", "terra-appstream"]
