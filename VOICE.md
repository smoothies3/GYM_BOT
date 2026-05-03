# GymBot — голос и тон бота

## Кто такой GymBot

Бро из зала. Не тренер, не корпоративный чат-бот, не мотивационный коуч.
Говорит как живой человек — который сам ходит в зал 5 лет, шутит над собой,
но и не даст пользователю слиться. Всегда на «ты».

## Принципы голоса

1. **На «ты», без пафоса.** Никогда «Вы», никогда «Здравствуйте».
2. **Коротко.** Максимум 3–4 строки на одно сообщение. В зале не читают эссе.
3. **Ирония — да, агрессия — нет.** Можно подколоть за лень, нельзя обвинить или задеть.
4. **Признаёт сложность.** Прийти в зал — уже усилие. Бот это знает.
5. **Конкретика.** «3 подхода по 10, 14 кг» — не «постарайся».
6. **Ситуативность.** Разные тексты на первый раз, стрик, возврат после паузы.

## Запрещено говорить

- «Здравствуйте / Вы / Необходимо / Рекомендуется»
- «Достижение разблокировано!» (казённо)
- «Ты такой молодец!!!!! 🎉🎉🎉» (лизательно, теряет доверие)
- «Ты совсем забил, лентяй!» (агрессия)
- Длинные лекции про сон, питание, режим — пользователь пришёл тренироваться

## Как использовать phrases.py

Все фразы бота живут в `bot/phrases.py`. Функция `p(key, **kwargs)` выбирает
случайный вариант и подставляет переменные.

```python
from bot.phrases import p

# Приветствие
text = p("workout_start_regular", name="Саня", day_key="A", workout_count=12)

# Карточка упражнения
text = p("exercise_card_intro",
         position=2, total=6, exercise="Жим гантелей лёжа",
         sets=3, reps_min=8, reps_max=12, weight=14)

# Конец тренировки
text = p("workout_finish_regular",
         volume_kg=3400, duration_min=52, xp=120, fc=100, workout_count=15)
```

## Ключи phrases.py — полный список

### Онбординг
| Ключ | Переменные |
|------|-----------|
| `onboarding_welcome` | `{name}` |
| `onboarding_ask_goal` | — |
| `onboarding_ask_level` | — |
| `onboarding_ask_days` | — |
| `onboarding_done` | — |

### Старт тренировки
| Ключ | Переменные | Когда |
|------|-----------|-------|
| `workout_start_first_ever` | `{name}` | Первая тренировка вообще |
| `workout_start_regular` | `{name}`, `{day_key}`, `{workout_count}` | Обычный день |
| `workout_start_streak_4w` | `{name}` | Стрик ровно 4 недели |
| `workout_start_streak_8w` | `{name}` | Стрик ровно 8 недель |
| `workout_start_streak_12w` | `{name}` | Стрик ровно 12 недель |
| `workout_start_comeback_1w` | — | Вернулся после 1 нед. паузы |
| `workout_start_comeback_2w` | — | Вернулся после 2 нед. паузы |
| `workout_start_comeback_3w_plus` | — | Вернулся после 3+ нед. паузы |
| `workout_start_first_of_week` | — | Первая тренировка в текущей неделе |

### Тренировочный флоу
| Ключ | Переменные |
|------|-----------|
| `exercise_card_intro` | `{position}`, `{total}`, `{exercise}`, `{sets}`, `{reps_min}`, `{reps_max}`, `{weight}` |
| `exercise_card_tip` | — (вставляется отдельной строкой) |
| `exercise_card_last` | — (показывать на последнем упражнении) |
| `rest_start` | `{seconds}` |
| `rest_end` | — |
| `rest_warning_30s` | — |
| `effort_easy` | — |
| `effort_on_point` | — |
| `effort_hard` | — |
| `replace_offer` | `{exercise}` |
| `replace_done` | — |

### Завершение тренировки
| Ключ | Переменные |
|------|-----------|
| `workout_finish_regular` | `{volume_kg}`, `{duration_min}`, `{xp}`, `{fc}`, `{workout_count}` |
| `workout_finish_overachieve` | `{fc}` |
| `workout_finish_first_of_week_bonus` | `{fc}` |
| `workout_finish_pb` | `{volume_kg}` |

### Стрик, бейджи, уровни
| Ключ | Переменные |
|------|-----------|
| `streak_week_complete` | `{streak_weeks}` |
| `streak_at_risk` | `{streak_weeks}` |
| `streak_lost` | — |
| `badge_earned` | `{badge_icon}`, `{badge_name}`, `{fc}` |
| `level_up` | `{old_level}`, `{new_level}`, `{avatar}`, `{avatar_name}`, `{fc}` |

### Напоминания
| Ключ | Переменные |
|------|-----------|
| `reminder_soft` | `{name}` |
| `reminder_evening` | `{gym_closes_in}` |
| `reminder_streak_save` | `{days_per_week}`, `{streak_weeks}` |

### Подписка
| Ключ | Переменные |
|------|-----------|
| `paywall_hit` | — |
| `subscription_activated` | — |
| `subscription_expiring_3d` | — |
| `subscription_expiring_1d` | — |
| `subscription_expired` | — |

### Прочее
| Ключ | Переменные |
|------|-----------|
| `error_generic` | — |
| `error_no_exercises` | — |
| `profile_header` | `{avatar}`, `{level}`, `{workout_count}`, `{volume_total_kg}`, `{streak_weeks}`, `{xp_total}`, `{fitcoin_balance}` |
| `shop_purchase_success` | `{item_name}`, `{fitcoin_balance}` |
| `shop_purchase_not_enough` | `{item_name}`, `{price_fc}`, `{fitcoin_balance}` |

## Приоритет фраз при старте тренировки

Выбирай ключ в таком порядке (первый подходящий побеждает):

```python
def get_workout_start_phrase(user, day_key: str) -> str:
    from bot.phrases import p

    name = user.first_name or "Бро"
    count = user.workout_count  # всего тренировок

    if count == 0:
        return p("workout_start_first_ever", name=name)

    weeks_since_last = user.weeks_since_last_workout  # нужно считать в сервисе

    if weeks_since_last >= 3:
        return p("workout_start_comeback_3w_plus")
    if weeks_since_last == 2:
        return p("workout_start_comeback_2w")
    if weeks_since_last == 1:
        return p("workout_start_comeback_1w")

    streak = user.streak_weeks
    if streak == 12:
        return p("workout_start_streak_12w", name=name)
    if streak == 8:
        return p("workout_start_streak_8w", name=name)
    if streak == 4:
        return p("workout_start_streak_4w", name=name)

    if user.current_week_workouts == 0:
        return p("workout_start_first_of_week")

    return p("workout_start_regular", name=name, day_key=day_key, workout_count=count)
```

## Правило новых фраз

Когда добавляешь новый хендлер или сообщение — **не пиши текст прямо в хендлере**.
Всегда добавляй ключ в `_PHRASES` в `phrases.py` с минимум 3 вариантами,
затем вызывай `p("ключ", ...)` в хендлере.

Это единственное место где живут все тексты бота.
