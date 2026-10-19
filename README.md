# AppStream metadata generator scripts

This repository contains a script to manage and generate AppStream metadata for Terra.

It does not however insert AppStream metadata into the repo yet, only generate them from inputs.

## Notes

This application is not a persistent service. It is meant to be run once periodically.

Depending on the need, a persistent server mode may be implemented later.

## Usage

```bash
BASE_DIR=/path/to/terra-mirror \
OUTPUT_DIR=/path/to/output/dir \
WORKSPACE_DIR=/path/to/asgen-workspace \
uv run terra-appstream
```

| Variable | Description |
|---|---|
| `BASE_DIR` | The mirror; every subdirectory with `repodata/repomd.xml` is one repo. |
| `OUTPUT_DIR` | Export root. It contains `<repo>/latest/appstream/{<repo>.xml.gz,<repo>-icons-64x64.tar.gz}`, which [Subatomic](https://github.com/FyraLabs/subatomic/tree/v0) injects into the repo's `repomd.xml` (point `SUBATOMIC_APPSTREAM_DIR` at this directory). On Terra, this is `$BASE_DIR/appstream`. It can be a network mount: only these finished files are written there. |
| `OLD_LIMIT` (optional, default 5) | Dated composes to keep per repo. |
| `WORKSPACE_DIR` | appstream-generator's workspace. Holds the package cache and its own export (`export/{data,hints,html,media}`, including the HTML report), so it must persist between runs. Keep it on a local disk. |
| `MEDIA_BASE_URL`, `HTML_BASE_URL` (optional) | Public URLs of `OUTPUT_DIR/media` and `OUTPUT_DIR/html`. |

## Linting RPMs

`terra-appstream-lint DIR` runs the same generator setup on the RPMs under `DIR` (searched
recursively, `.src.rpm` skipped) in a throwaway repo and workspace, and prints the components it
would publish and every hint, with severity and message.

```bash
uv run terra-appstream-lint [--fail-on error|warning|never] [--report-dir OUT] DIR
```

- `--fail-on`: exit 1 if any hint reaches this severity (default `error`; `never` always passes).
  Exit 2 means nothing could be checked (no RPMs, or appstream-generator failed).
- `--report-dir`: also copy appstream-generator's export directory (`data`, `hints`, `html`,
  `media`) to `OUT`, unchanged. The HTML report links its assets at the site root (`/static/`,
  `/pool/`), so serve it rather than opening the files: `OUT/html` at the site root for the pages
  and styles (e.g. `python3 -m http.server -d OUT/html`), plus `OUT/media/pool` at `/pool/` for icons.

It needs appstream-generator and `createrepo_c`, so run it in the image (or `scripts/dev.sh`).
See [Using as a GitHub Action](#using-as-a-github-action) for CI.

## Requirements

- [uv](https://astral.sh/uv)
- [appstream-generator](https://github.com/ximion/appstream-generator) 1.0 (built by the Dockerfile)

## Using as a GitHub Action

You can use this repository as a reusable GitHub Action that lints a directory of RPMs:

```yaml
- uses: terrapkg/appstream-generator@main
  with:
    path: build/rpms
    fail-on: error
    upload_report: true
```

The action can be configured with the following inputs:

| Input | Description | Default |
|---|---|---|
| `path` | Directory containing the RPMs to check (searched recursively; `.src.rpm` files are skipped). Required. | |
| `fail-on` | Fail the step on `error` hints, on `warning` hints (and errors), or `never`. | `error` |
| `image` | Container image with appstream-generator and `terra-appstream-lint`. | `ghcr.io/terrapkg/appstream-generator:main` |
| `upload_report` | Upload appstream-generator's export (HTML report, hints, catalog, icons) as an artifact. It is uploaded even when the lint fails. | `false` |
| `report_name` | Artifact name for the report. | `appstream-report-<run id>-<attempt>` |

Hints show up as annotations (errors, warnings, and notices for info/pedantic hints), and a table of
components and hints is added to the job summary.

Artifact names must be unique within a workflow run, and the default `report_name` is the same for
every job in a run. In a matrix, set it per job, e.g. `report_name: appstream-report-${{ matrix.arch }}`.

The action runs `docker`, so it needs a Linux runner with Docker (GitHub-hosted Ubuntu runners
work). On self-hosted runners with SELinux enforcing, the RPM directory mount isn't readable.
