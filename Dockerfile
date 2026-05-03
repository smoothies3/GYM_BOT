FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    "aiogram>=3.7.0" \
    "sqlalchemy[asyncio]>=2.0" \
    "asyncpg>=0.29.0" \
    "alembic>=1.13.0" \
    "apscheduler>=3.10.4" \
    "pydantic-settings>=2.3.0" \
    "python-dotenv>=1.0.0"

COPY . .

CMD ["python", "-m", "bot.main"]
