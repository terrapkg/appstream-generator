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
BASE_DIR=/path/to/terra-mirror
OUTPUT_DIR=/path/to/output/dir # On Terra, we just do $BASE_DIR/appstream
```

## Requirements

- [uv](https://astral.sh/uv)
- appstream-builder (glib)

