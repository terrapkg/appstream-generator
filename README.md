# AppStream metadata generator scripts

This repository contains a script to manage and generate AppStream metadata for Terra.

It does not however insert AppStream metadata into the repo yet, only generate them from inputs.

## Notes

This application is not a persistent service. It is meant to be run once periodically.
In production we use [K8s Cron jobs](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
to schedule generation tasks.

Depending on the need, a persistent server mode may be implemented later.

## Usage

```bash
BASE_DIR=/path/to/terra-mirror \
OUTPUT_DIR=/path/to/output/dir \
WORKSPACE_DIR=/path/to/asgen-workspace \
uv run terra-appstream
```

- `BASE_DIR`: the mirror; every subdirectory with `repodata/repomd.xml` is one repo.
- `OUTPUT_DIR`: export root. It contains `<repo>/latest/appstream/{<repo>.xml.gz,<repo>-icons-64x64.tar.gz}`,
  which [Subatomic](https://github.com/FyraLabs/subatomic/tree/v0) injects into the repo's `repomd.xml`
  (point `SUBATOMIC_APPSTREAM_DIR` at this directory). It also contains appstream-generator's own export in
  `{data,hints,html,media}/<repo>/main/`. On Terra, this is `$BASE_DIR/appstream`.
- `OLD_LIMIT` (optional, default 5): dated composes to keep per repo.
- `WORKSPACE_DIR`: appstream-generator's workspace. Holds the package cache, so it must
  persist between runs and should not be publicly served.
- `MEDIA_BASE_URL`, `HTML_BASE_URL` (optional): public URLs of `OUTPUT_DIR/media` and `OUTPUT_DIR/html`.

## Requirements

- [uv](https://astral.sh/uv)
- [appstream-generator](https://github.com/ximion/appstream-generator) 1.0 (built by the Dockerfile)

