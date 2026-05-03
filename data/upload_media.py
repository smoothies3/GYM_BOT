"""
Upload exercise videos/GIFs to Telegram and cache file_ids in media/file_ids.json.

Usage (from project root):
    python -m data.upload_media

Naming convention — put files in media/exercises/ named exactly as the exercise:
    media/exercises/Жим гантелей лёжа.mp4
    media/exercises/Подтягивания.gif
    media/exercises/Приседания со штангой.mp4
    ...

Supported formats: .mp4  .gif  .mov  .avi
After running, media/file_ids.json is updated with Telegram file_ids.
Re-running only uploads new/missing files.
"""
import asyncio
import json
from pathlib import Path

from aiogram import Bot

from bot.config import settings

MEDIA_DIR = Path(__file__).parent.parent / "media" / "exercises"
CACHE_FILE = Path(__file__).parent.parent / "media" / "file_ids.json"
SUPPORTED = {".mp4", ".gif", ".mov", ".avi"}


def load_cache() -> dict:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict) -> None:
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


async def upload_all() -> None:
    cache = load_cache()
    bot = Bot(token=settings.BOT_TOKEN)

    # Use admin's Telegram ID to send upload messages
    admin_ids = settings.get_admin_ids()
    if not admin_ids:
        print("ERROR: Set ADMIN_IDS in .env — we need a chat_id to upload files.")
        await bot.session.close()
        return
    chat_id = admin_ids[0]

    files = [f for f in MEDIA_DIR.iterdir() if f.suffix.lower() in SUPPORTED]
    if not files:
        print(f"No files found in {MEDIA_DIR}")
        await bot.session.close()
        return

    uploaded, skipped = 0, 0
    for filepath in sorted(files):
        name = filepath.stem  # filename without extension = exercise name
        if name in cache:
            print(f"  skip  {name}")
            skipped += 1
            continue

        print(f"  upload {name} ...", end=" ", flush=True)
        try:
            from aiogram.types import FSInputFile
            file = FSInputFile(filepath)
            if filepath.suffix.lower() == ".gif":
                msg = await bot.send_animation(chat_id, file, caption=name)
                file_id = msg.animation.file_id
            else:
                msg = await bot.send_video(chat_id, file, caption=name)
                file_id = msg.video.file_id

            cache[name] = file_id
            save_cache(cache)
            print(f"OK  (file_id: {file_id[:20]}...)")
            uploaded += 1
        except Exception as e:
            print(f"FAIL: {e}")

    await bot.session.close()
    print(f"\nDone: {uploaded} uploaded, {skipped} skipped.")
    print(f"Cache saved to {CACHE_FILE}")


if __name__ == "__main__":
    asyncio.run(upload_all())
