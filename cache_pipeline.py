"""Standard-library-only offline video cache. No API credentials are stored here."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from layer_cache import key_lock

VERSION = 1
MEDIA_NAMES = {".mp4", ".webm", ".mov"}


def read_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if config.get("schema_version") != VERSION:
        raise ValueError("Unsupported configuration schema")
    for name in ("character", "scene", "quality", "performance", "generator"):
        if not isinstance(config.get(name), dict) or not config[name]:
            raise ValueError(f"Missing configuration section: {name}")
    quality = config["quality"]
    for name in ("width", "height", "fps"):
        value = quality.get(name)
        if type(value) is not int or value <= 0:
            raise ValueError(f"quality.{name} must be a positive integer")
    if config["generator"].get("id") == "blender-offline-v1":
        from render_settings import resolve
        config = resolve(config)
    elif config['generator'].get('id')=='scanned-blender-v1':
        from scanned_settings import resolve
        config=resolve(config)
    return config


def cache_key(config):
    data = json.dumps({"cache_schema": VERSION, "config": config},
                      sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def lookup(root, config):
    directory = Path(root) / cache_key(config)
    try:
        manifest = json.loads((directory / "manifest.json").read_text("utf-8"))
        filename = manifest["media"]
        if filename not in {"video.mp4", "video.webm", "video.mov"}:
            return None
        media = directory / filename
        if (manifest["key"] != cache_key(config) or manifest["config"] != config
                or media.stat().st_size == 0 or digest(media) != manifest["sha256"]):
            return None
        return media
    except (OSError, ValueError, KeyError, TypeError):
        return None


def publish(root, config, source):
    source = Path(source).resolve()
    if source.suffix.lower() not in MEDIA_NAMES or not source.is_file():
        raise ValueError("Provide a rendered .mp4, .webm or .mov video")
    if not source.stat().st_size:
        raise ValueError("Video is empty")
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    key = cache_key(config)
    destination = root / key
    stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=root))
    try:
        filename = "video" + source.suffix.lower()
        shutil.copyfile(source, stage / filename)
        manifest = {"schema_version": VERSION, "key": key, "config": config,
                    "media": filename, "sha256": digest(stage / filename),
                    "created_at_unix": time.time(), "playback": "cached-video"}
        (stage / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        # Preserve an earlier entry on replacement; no recursive deletion of caches.
        backup = None
        if destination.exists():
            backup = root / (key + ".previous-" + uuid.uuid4().hex)
            destination.rename(backup)
        try:
            stage.rename(destination)
        except OSError:
            if backup:
                backup.rename(destination)
            raise
        return destination / filename
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def generate(root, config, command):
    """Run an explicitly configured argv; never interpolate into a shell."""
    if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
        raise ValueError("Renderer command must be a nonempty JSON array of strings")
    if not any("{output}" in arg for arg in command):
        raise ValueError("Renderer command must include {output}")
    with tempfile.TemporaryDirectory(prefix="digitalhuman-render-") as temporary:
        output = Path(temporary) / "video.mp4"
        # Pass a snapshot so generated content matches the configuration being hashed.
        snapshot = Path(temporary) / "config.json"
        snapshot.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        argv = [arg.replace("{config}", str(snapshot)).replace("{output}", str(output))
                .replace("{python}", sys.executable).replace("{project}", str(Path(__file__).resolve().parent))
                for arg in command]
        subprocess.run(argv, check=True, shell=False)
        return publish(root, config, output)


def main(argv=None):
    parser = argparse.ArgumentParser(description="数字人：离线生成与缓存回放")
    parser.add_argument("action", choices=["status", "import", "prepare", "play"])
    parser.add_argument("--config", default="prototype.json")
    parser.add_argument("--cache", default=".cache/digitalhuman")
    parser.add_argument("--video", help="Previously rendered video, with synchronized audio")
    parser.add_argument("--command-file", help="JSON argv array for external renderer")
    parser.add_argument("--force", action="store_true", help="Explicitly regenerate / replace")
    parser.add_argument("--dry-run", action="store_true", help="Resolve playback without opening player")
    args = parser.parse_args(argv)
    try:
        config = read_config(args.config)
        media = lookup(args.cache, config)
        if args.action == "status":
            print(json.dumps({"key": cache_key(config), "hit": media is not None,
                              "video": str(media.resolve()) if media else None}, ensure_ascii=False))
            return 0
        if args.action in {"prepare", "import"}:
            if media and not args.force:
                print("CACHE HIT: generation skipped")
            else:
                with key_lock(args.cache, cache_key(config)):
                    media = lookup(args.cache, config)
                    if media and not args.force:
                        print("CACHE HIT: generation skipped")
                    elif args.action == "import":
                        if not args.video:
                            raise ValueError("import requires --video")
                        media = publish(args.cache, config, args.video)
                    else:
                        if not args.command_file:
                            raise ValueError("Cache miss: configure external renderer with --command-file, or import a video")
                        command = json.loads(Path(args.command_file).read_text("utf-8-sig"))
                        media = generate(args.cache, config, command)
        if not media:
            raise ValueError("Cache miss or damaged cache: run prepare / import first; play never calls APIs")
        print("CACHED VIDEO / 缓存回放: " + str(media.resolve()))
        if args.action == "play" and not args.dry_run:
            if sys.platform != "win32":
                raise ValueError("Automatic player launch is Windows-only; open the printed file manually")
            os.startfile(str(media.resolve()))
        return 0
    except (OSError, ValueError, TypeError, subprocess.CalledProcessError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
