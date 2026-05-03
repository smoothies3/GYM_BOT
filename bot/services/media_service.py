"""
Resolves exercise media: returns a cached Telegram file_id or a local FSInputFile.
Falls back silently — missing media is never a fatal error.
"""
import json
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile, InputMediaAnimation, InputMediaVideo

MEDIA_DIR = Path(__file__).parent.parent.parent / "media" / "exercises"
CACHE_FILE = Path(__file__).parent.parent.parent / "media" / "file_ids.json"
SUPPORTED = [".mp4", ".gif", ".mov", ".avi"]

_cache: dict | None = None


def _load_cache() -> dict:
    global _cache
    if _cache is None:
        _cache = json.loads(CACHE_FILE.read_text(encoding="utf-8")) if CACHE_FILE.exists() else {}
    return _cache


def _save_cache() -> None:
    if _cache is not None:
        CACHE_FILE.write_text(json.dumps(_cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_local_file(exercise_name: str) -> Path | None:
    for ext in SUPPORTED:
        path = MEDIA_DIR / f"{exercise_name}{ext}"
        if path.exists():
            return path
    return None


async def send_exercise_media(bot: Bot, chat_id: int, exercise_name: str) -> bool:
    """Send video/GIF for the exercise. Returns True if something was sent."""
    cache = _load_cache()

    # Cached file_id — fastest path
    if exercise_name in cache:
        file_id = cache[exercise_name]
        try:
            await bot.send_animation(chat_id, file_id)
            return True
        except Exception:
            # file_id stale — remove and try local
            cache.pop(exercise_name, None)

    # Local file — upload and cache
    local = _find_local_file(exercise_name)
    if not local:
        return False

    try:
        file = FSInputFile(local)
        if local.suffix.lower() == ".gif":
            msg = await bot.send_animation(chat_id, file)
            cache[exercise_name] = msg.animation.file_id
        else:
            msg = await bot.send_video(chat_id, file)
            cache[exercise_name] = msg.video.file_id
        _save_cache()
        return True
    except Exception:
        return False
