import concurrent.futures
import logging
import os
import shutil
import subprocess
from threading import Thread

from dotenv import load_dotenv
from logfmter import Logfmter

logger = logging.getLogger("appstream-generator")


handler = logging.StreamHandler()
handler.setFormatter(Logfmter(keys=["level", "name"], mapping={"level": "levelname"}))
logging.basicConfig(handlers=[handler], level=logging.INFO)

# logging.error({"token": "Hello, World!"}) # at=ERROR token="Hello, World!"


# should be self-explanatory lol
# note: this is for DX, not really needed
_dotenv = load_dotenv()

required_envars = ["BASE_DIR", "OUTPUT_DIR"]

missing_vars = [var for var in required_envars if var not in os.environ]
if missing_vars:
    raise EnvironmentError(
        f"Missing required environment variable(s): {', '.join(missing_vars)}"
    )

base_dir = os.environ["BASE_DIR"]
out_dir = os.environ["OUTPUT_DIR"]

# Limits N number of old entries
old_limit = int(os.environ.get("OLD_LIMIT", 5))

# Max concurrent tasks
max_workers = int(os.environ.get("MAX_WORKERS", 5))


def scan_base_dir(base_dir: str):
    for entry in os.scandir(base_dir):
        if entry.is_dir():
            if entry.path == out_dir:
                continue
            yield entry.path


def format_output_path(out_dir: str, repo_name: str):
    from datetime import datetime

    date_str = datetime.now().strftime("%Y%m%d%H%M")
    return os.path.join(out_dir, repo_name, date_str)


# What this does is:
# - Scan the base directory for subdirectories
# - run appstream-builder on them and output to formatted dir
# - outputs are formatted in <repo>/<date>
# - latest run gets symlinked to latest


def log_stream(stream, logger_obj):
    """Read from stream and log each flush (buffered output)"""
    buffer = ""
    while True:
        chunk = stream.read(4096)
        if not chunk:
            break
        buffer += chunk
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.rstrip()
            if line:
                # Parse log level from message
                level = logging.INFO  # default
                if "DEBUG:" in line:
                    level = logging.DEBUG
                elif "WARNING:" in line:
                    level = logging.WARNING
                elif "ERROR:" in line:
                    level = logging.ERROR
                elif "CRITICAL:" in line:
                    level = logging.CRITICAL

                logger_obj.log(level, line)
    # Log any remaining buffered output
    if buffer.strip():
        logger_obj.info(buffer.strip())
    stream.close()


def build_appstream(path: str, output_dir: str):
    repo_name = os.path.basename(path)
    logger = logging.getLogger(f"builder-{repo_name}")
    appstream_builder = "appstream-builder"
    args = [
        "--verbose",
        "--veto-ignore=missing-parents",
        "--veto-ignore=missing-info",
        "--output-dir",
        f"{output_dir}/appstream",
        "--temp-dir",
        "/tmp/appstream",
        "--icons-dir",
        f"{output_dir}/icons",
        "--cache-dir",
        f"{output_dir}/cache",
        "--basename",
        repo_name,
        "--log-dir",
        f"{output_dir}/logs",
        "--include-failed",
        "--origin",
        "terra",
        "--packages-dir",
        path,
        "--old-metadata",
        f"{output_dir}../latest/appstream",
    ]

    full_args = [appstream_builder] + args
    try:
        process = subprocess.Popen(
            full_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        stdout_thread = Thread(
            target=log_stream,
            args=(
                process.stdout,
                logger,
            ),
        )
        stderr_thread = Thread(
            target=log_stream,
            args=(
                process.stderr,
                logger,
            ),
        )

        stdout_thread.start()
        stderr_thread.start()

        process.wait()

        stdout_thread.join()
        stderr_thread.join()

    except Exception as e:
        logger.error(f"Error running appstream-builder: {e}")
        raise
    # finally:
    # return output_dir

    # now go to output_dir/icons
    screenshots_dir = os.path.join(output_dir, "icons")
    logger.info(f"Checking for screenshots in {screenshots_dir}")
    if os.path.exists(screenshots_dir):
        for dir in os.scandir(screenshots_dir):
            logger.info(f"found screenshots dir at {dir.path}")
            if dir.is_dir():
                proc = subprocess.Popen(
                    [
                        "tar",
                        "-C",
                        dir.path,
                        "-czf",
                        os.path.join(
                            output_dir,
                            "appstream",
                            f"{repo_name}-icons-{dir.name}.tar.gz",
                        ),
                        ".",
                        "--strip-components=2",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                stdout_thread = Thread(
                    target=log_stream,
                    args=(
                        proc.stdout,
                        logger,
                    ),
                )
                stderr_thread = Thread(
                    target=log_stream,
                    args=(
                        proc.stderr,
                        logger,
                    ),
                )
                stdout_thread.start()
                stderr_thread.start()

                process.wait()

                stdout_thread.join()
                stderr_thread.join()

    return output_dir


def cleanup_old_composes(basedir: str):
    composes = sorted(
        [
            d
            for d in os.listdir(basedir)
            if os.path.isdir(os.path.join(basedir, d))
            and not os.path.islink(os.path.join(basedir, d))
        ],
        reverse=True,
    )

    logger.info(
        {
            "msg": "Found composes",
            "compose_count": len(composes),
            "operation": "cleanup",
            "compose_list": composes,
        },
    )

    # Now keep only N most recent, delete the rest
    # don't delete symlinks or non-dirs
    to_delete = composes[old_limit:]
    if not to_delete:
        logger.info(
            {
                "msg": f"No old composes to delete, keeping all {len(composes)}",
                "operation": "cleanup",
            }
        )
        return
    else:
        logger.info(
            {
                "msg": f"Keeping {old_limit} most recent composes, removing {len(to_delete)} old ones",
                "operation": "cleanup-delete",
            }
        )
    for dir in to_delete:
        full_path = os.path.join(basedir, dir)
        try:
            logger.info(
                {
                    "msg": f"Removing old compose at {full_path}",
                    "operation": "cleanup-delete",
                    "path": full_path,
                }
            )
            shutil.rmtree(full_path)
        except Exception as e:
            logger.error(f"Error removing old compose at {full_path}: {e}")


def process_repo(path: str):
    # shadow global logger, we're gonna do our own thing
    repo_name = os.path.basename(path)
    logger = logging.getLogger(repo_name)

    out_base_dir = os.path.join(out_dir, repo_name)
    logger.info(f"Processing repo at {path}")
    compose_out = format_output_path(out_dir, repo_name)
    logger.info(f"Outputting to {compose_out}")

    try:
        # hack: symlink os/repodata to repodata in the path
        repodata_src = os.path.join(path, "repodata")
        os_dir = os.path.join(path, "os")
        os.makedirs(os_dir, exist_ok=True)
        os_repodata_link = os.path.join(os_dir, "repodata")
        if not os.path.exists(os_repodata_link) and os.path.exists(repodata_src):
            logger.info(f"Linking {os_repodata_link} to {repodata_src}")
            os.symlink(repodata_src, os_repodata_link)
        # end symlink
        os.makedirs(compose_out, exist_ok=True)
        output = build_appstream(path, compose_out)
        latest_path = os.path.join(out_base_dir, "latest")
        logger.info(f"Linking latest to {latest_path}")
        # ln -sf
        if os.path.islink(latest_path) or os.path.exists(latest_path):
            os.remove(latest_path)
        # Create a relative symlink from latest_path to output
        rel_output = os.path.relpath(output, os.path.dirname(latest_path))
        os.symlink(rel_output, latest_path)
        logger.info(f"Symlinked latest to {latest_path} (-> {rel_output})")

        cleanup_old_composes(out_base_dir)

    except Exception as e:
        logger.error(f"Error processing repo {repo_name}: {e}")
        return
    finally:
        return True


def main():
    # setup_logging()
    # logger.info("test")
    thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
    futures = []
    for dir in scan_base_dir(base_dir):
        futures.append(thread_pool.submit(process_repo, dir))
    _ = concurrent.futures.wait(futures)
    thread_pool.shutdown(wait=True)
    thread_pool = None


if __name__ == "__main__":
    main()
