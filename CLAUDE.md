# GymBot — контекст проекта для Claude Code

## Что это

Telegram-бот для тренировок в зале. Целевая аудитория — люди в России без бюджета на тренера ("Low-Effort" сегмент). Бот работает как навигатор: пришёл в зал → нажал кнопку → получил упражнение → сделал → нажал "Готово" → следующее.

## Технологический стек

- **Python 3.11+**
- **aiogram 3.x** — асинхронный Telegram-бот
- **PostgreSQL** — основная БД
- **SQLAlchemy (async)** — ORM
- **Alembic** — миграции
- **APScheduler** — таймеры отдыха и cron-задачи
- **ЮKassa** через Telegram Payments — оплата
- **Docker + docker-compose** — окружение

## Структура проекта

```
gymbot/
├── bot/
│   ├── main.py                  # точка входа, polling
│   ├── config.py                # Pydantic Settings, .env
│   ├── handlers/
│   │   ├── start.py             # /start, онбординг
│   │   ├── workout.py           # основной флоу тренировки
│   │   ├── payments.py          # invoice, pre_checkout, successful_payment
│   │   ├── profile.py           # профиль, статистика, магазин
│   │   └── admin.py             # admin-команды (is_admin=True)
│   ├── middlewares/
│   │   ├── db.py                # инжектит AsyncSession в хендлеры
│   │   ├── auth.py              # проверяет подписку, блокирует если просрочена
│   │   └── throttling.py        # антиспам
│   ├── services/
│   │   ├── user_service.py      # работа с профилем
│   │   ├── workout_service.py   # выдача упражнений, замена, сессия
│   │   ├── progress_service.py  # алгоритм прогрессии весов
│   │   ├── gamification.py      # XP, стрик, бейджи, Fitcoin, уровни
│   │   └── payment_service.py   # ЮKassa, активация подписки
│   ├── models/
│   │   ├── base.py              # DeclarativeBase, TimestampMixin
│   │   ├── user.py              # Users
│   │   ├── exercise.py          # Exercises
│   │   ├── workout.py           # WorkoutPlans, PlanExercises, WorkoutSessions
│   │   └── log.py               # ExerciseLogs, ProgressWeights, Subscriptions,
│   │                            #   Badges, UserBadges, FitcoinTransactions,
│   │                            #   ShopItems, UserPurchases
│   ├── keyboards/
│   │   ├── onboarding.py
│   │   ├── workout.py
│   │   └── common.py
│   └── states/
│       └── fsm.py               # OnboardingFSM, WorkoutFSM
├── migrations/                  # Alembic
├── data/                        # seed-файлы упражнений (JSON)
├── tests/
├── docker-compose.yml
├── .env.example
└── pyproject.toml
```

## База данных — таблицы

### USERS
```
id uuid PK | telegram_id bigint UK | username varchar | first_name varchar
goal varchar (mass/cut/tone) | level varchar (beginner/mid/adv)
gender varchar | days_per_week int
is_subscribed bool | sub_expires_at timestamp | trial_used bool | is_admin bool
xp_total int | level int | epoch varchar
streak_weeks int | current_week_workouts int | week_started_at date
fitcoin_balance int | fitcoin_total_earned int | avatar_skin_id uuid FK
created_at timestamp | updated_at timestamp
```

### EXERCISES
```
id uuid PK | name varchar | muscle_group varchar (IDX) | equipment varchar
difficulty varchar | media_url varchar | description text | tips text
alternative_ids json | is_active bool
```

### WORKOUT_PLANS
```
id uuid PK | name varchar | goal varchar | level varchar
days_per_week int | is_active bool
```

### PLAN_EXERCISES
```
id uuid PK | plan_id uuid FK | exercise_id uuid FK
day_key varchar (A/B/C) | position int | sets int | reps_min int | reps_max int
```

### WORKOUT_SESSIONS
```
id uuid PK | user_id uuid FK | plan_id uuid FK | day_key varchar
current_ex_index int | status varchar (active/finished/abandoned)
started_at timestamp | finished_at timestamp
total_volume_kg int | duration_min int | xp_earned int
```

### EXERCISE_LOGS
```
id uuid PK | session_id uuid FK | exercise_id uuid FK | user_id uuid FK
set_number int | weight_kg float | reps int
effort varchar (easy/on_point/hard) | was_replaced bool | logged_at timestamp
```

### PROGRESS_WEIGHTS
```
id uuid PK | user_id uuid FK | exercise_id uuid FK
recommended_kg float | last_weight_kg float | last_effort varchar | easy_streak int
updated_at timestamp
```

### BADGES
```
id uuid PK | code varchar UK | name varchar | description varchar
icon varchar | condition_type varchar | condition_value int
```

### USER_BADGES
```
id uuid PK | user_id uuid FK | badge_id uuid FK | earned_at timestamp
```

### SUBSCRIPTIONS
```
id uuid PK | user_id uuid FK | status varchar (active/expired/cancelled)
provider_payment_id varchar | amount_kopecks int
started_at timestamp | expires_at timestamp | created_at timestamp
```

### FITCOIN_TRANSACTIONS
```
id uuid PK | user_id uuid FK
amount int (положительный = приход, отрицательный = трата)
reason varchar (workout/badge/level_up/purchase/streak_bonus/overachieve)
ref_id uuid | created_at timestamp
```

### SHOP_ITEMS
```
id uuid PK | name varchar | category varchar (cosmetic/program/content/util)
price_fc int | content_url varchar | level_required int | is_active bool
```

### USER_PURCHASES
```
id uuid PK | user_id uuid FK | item_id uuid FK
price_paid_fc int | purchased_at timestamp
```

## FSM-состояния

```python
class OnboardingFSM(StatesGroup):
    gender = State()
    goal   = State()
    level  = State()
    days   = State()

class WorkoutFSM(StatesGroup):
    exercise_card  = State()  # показ карточки упражнения
    rating_effort  = State()  # оценка усилия (easy/on_point/hard)
    rest_timer     = State()  # ожидание таймера отдыха
    replacing      = State()  # выбор замены упражнения
    finished       = State()  # итоговый экран
```

## Ключевые алгоритмы

### Прогрессия весов
```python
PROGRESSION_STEP = {
    "barbell": 2.5, "dumbbell": 2.0,
    "machine": 5.0, "cable": 2.5, "bodyweight": 0.0
}

# easy → +step (если easy_streak >= 2: +step*2)
# on_point → без изменений
# hard → -step (не ниже минимума)
# Округлять до ближайшего кратного шагу
```

### XP за тренировку
```python
xp = (base_xp + volume_bonus + effort_bonus) * streak_multiplier

# base_xp = 50
# volume_bonus = total_volume_kg // 1000 * 10
# effort_bonus = on_point_count * 5 + hard_count * 3
# streak_multiplier: 1-2нед=1.0, 3-6нед=1.1, 7-13нед=1.25, 14-29нед=1.5, 30+нед=2.0
# Если current_week_workouts > days_per_week: xp *= 1.5  (перевыполнение)
```

### XP для уровня N
```python
xp_for_level = int(100 * (1.15 ** n))
```

### Недельный стрик (не дневной!)
```python
# Стрик считается по неделям, НЕ по дням
# Неделя засчитана если: current_week_workouts >= days_per_week
# Сброс: если неделя закончилась и цель не выполнена
# Граница недели — понедельник 00:00 по МСК
```

### Fitcoin — начисление
```
Тренировка завершена:     +100 FC
Оценка «В точку»:         +5 FC за упражнение
Бонус за стрик недели:    +50 FC
Перевыполнение недели:    +75 FC
Новый бейдж:              +200 FC
Повышение уровня:         +50 до +2000 FC (зависит от уровня)
Первая тренировка недели: +30 FC
```

## Монетизация

- **Первая тренировка бесплатно**, затем жёсткий paywall
- **Тарифы**: 299 ₽/мес | 762 ₽/3 мес (−15%) | 2868 ₽/год (−20%)
- **Telegram Payments + ЮKassa** — разовые платежи (не рекуррентные)
- **SubscriptionMiddleware** — проверяет подписку на каждый update
- **pre_checkout_query** — обязателен, ответ в течение 10 сек
- Напоминание о продлении за 3 дня и за 1 день до истечения

## Бейджи (15 штук)

| Код | Условие |
|-----|---------|
| first_workout | Первая тренировка |
| subscriber | Оформить подписку |
| onboarded | Пройти онбординг |
| streak_4w | Стрик 4 недели |
| streak_8w | Стрик 8 недель |
| streak_12w | Стрик 12 недель |
| volume_50k | Объём 50 000 кг |
| volume_200k | Объём 200 000 кг |
| volume_10k_session | 10 000 кг за тренировку |
| workouts_10 | 10 тренировок |
| workouts_25 | 25 тренировок |
| workouts_50 | 50 тренировок |
| workouts_100 | 100 тренировок |
| on_point_master | 5 оценок «В точку» за тренировку |
| adaptive | Замена упражнения 10 раз |

## Аватар (Тамагочи-лайт)

Статичная эмодзи-картинка, меняется автоматически с уровнем:
- Ур. 1: 🧍 Новичок
- Ур. 5: 🚶 Ходок
- Ур. 10: 🏃 Бегун
- Ур. 25: 🏋️ Атлет
- Ур. 50: 💪 Профи
- Ур. 100: 🦁 Элита
- Ур. 250: ⚡ Легенда

## Важные решения (не менять без причины)

1. **Стрик недельный, не дневной** — у пользователя цель 2–3 тренировки в неделю, пропуск 3 дней это норма
2. **XP не тратится** — только растёт. Fitcoin тратится. Разные роли.
3. **amount_kopecks int** — деньги никогда в float
4. **is_admin в USERS** — не отдельная таблица, для одного разработчика достаточно
5. **alternative_ids JSON в EXERCISES** — проще чем таблица связей на MVP
6. **was_replaced bool в EXERCISE_LOGS** — аналитика по популярности замен
7. **easy_streak в PROGRESS_WEIGHTS** — избегаем дорогого запроса к истории
8. **Разовые платежи, не рекуррентные** — рекуррентность в v2
9. **Хендлеры не содержат бизнес-логику** — только вызов сервисов
10. **pre_checkout_query всегда пропускается в middleware** — иначе оплата сломается

## Порядок разработки (8 недель)

1. **Нед 1–2**: настройка проекта, БД, модели, Alembic, онбординг + FSM
2. **Нед 3–4**: тренировочный флоу, EXERCISE_CARD, RATING_EFFORT, REST_TIMER, замена
3. **Нед 5**: прогрессия весов, XP, недельный стрик, Fitcoin, бейджи
4. **Нед 6**: ЮKassa, paywall, pre_checkout_query, напоминания о продлении
5. **Нед 7**: наполнение БД (35–40 упражнений, 4 шаблона программ)
6. **Нед 8**: тестирование, деплой на VPS, мониторинг (Sentry)

## Текущий статус

- [ ] Проект создан
- [ ] docker-compose.yml настроен
- [ ] Модели БД написаны
- [ ] Alembic настроен
- [ ] Онбординг работает
- [ ] Тренировочный флоу работает
- [ ] Геймификация работает
- [ ] Оплата работает
- [ ] База упражнений заполнена
- [ ] Деплой выполнен

## Голос бота

Все тексты которые бот отправляет пользователям живут в `bot/phrases.py`.
Подробный гайд по тону и правилам — в `VOICE.md`.

**Правило:** при добавлении любого нового сообщения —
не пиши текст прямо в хендлере. Добавь ключ в `_PHRASES`
с минимум 3 вариантами, затем вызывай `p("ключ", ...)`.
