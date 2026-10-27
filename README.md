Текущий [аудит API/MCP и сценариев](docs/INTEGRATION_AUDIT.md): реальные ответы источников, найденные сбои и ограничения.

# Веб-приложение и Telegram

React-интерфейс **О! рядом** и бот
[@ostrovok_helper_ryadom_bot](https://t.me/ostrovok_helper_ryadom_bot) используют
один FastAPI, LangGraph и PostgreSQL: профиль, история, пошаговый выбор,
имитация оплаты, маршрутный PDF и сопровождение.
[Запуск и документация](docs/WEB_AND_TELEGRAM.md).

```bash
docker compose up
```

В корневом `.env` нужны `MODEL`, `TOKEN`, `BASE_URL`,
`TRAVEL_POSTGRES_PASSWORD`, `TELEGRAM_BOT_TOKEN` (имена есть в `.env.example`).
Compose поднимает PostgreSQL, backend с API, агентами и Telegram-ботом, а также
отдельный `frontend` с React и nginx. Сайт: [localhost:8000](http://127.0.0.1:8000).
После изменения кода: `docker compose up --build`. Запуск без Docker
и подробности конфигурации описаны в [документации](docs/WEB_AND_TELEGRAM.md).

Фронтенд можно пересобрать отдельно: `docker compose up -d --build frontend`.

Текущая оркестрация: Supervisor → независимые ReAct-специалисты параллельно → проверка фактов и совместимости → до пяти вариантов с программой и объяснением. Есть один адресный круг исправлений и точечные изменения. [Архитектура, проверки и запуск диалога](docs/AUTONOMOUS_PLANNING.md). Старый пошаговый режим доступен через `create_app(autonomous=False)`.

Проверить диалог как пользователь: `python chat.py` — один процесс, без отдельного сервера, только пользовательские ответы; поездка сохраняется локально. [Подробная инструкция](docs/TRAVEL_AGENT.md).

Рабочий backend Travel Agent: [запуск, CLI, API и ограничения](docs/TRAVEL_AGENT.md). [Результаты проверок](docs/TRAVEL_AGENT_VALIDATION.md).

# Flinters: исследование API/MCP для Большого Сочи

Этапы 1–2 выполнены. Это воспроизводимый исследовательский стенд, а не полноценный travel agent. Проверены реальные ответы с предоставленными ключами и публичные источники; недоступные интеграции имеют конкретные причины пропуска.

- [Рекомендуемый стек](docs/RECOMMENDED_STACK.md)
- [Сравнение, измерения и оценки](docs/API_COMPARISON.md)
- [Результаты MCP и схемы инструментов](docs/MCP_TEST_RESULTS.md)
- [Эксперименты с LLM и выявленные ошибки](docs/LLM_EXPERIMENTS.md)
- [Архитектура и последовательность реализации](docs/ARCHITECTURE_PROPOSAL.md)
- [Каталог и ограничения](docs/API_CATALOG.md), [ключи](docs/API_KEYS_SETUP.md), [безопасность MCP](docs/MCP_SECURITY_REVIEW.md)
- [Машиночитаемый итог](reports/integration_results.json), [нормализованные ответы](reports/normalized_results.json), [котировки Tutu](reports/tutu_normalized.json)

Python 3.13.7 проверен; community MCP требует >=3.12. Настройки `.env` не меняются. В PyCharm выбрать `.venv/bin/python`.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
```

Повторить весь набор одной командой (ключи локально в `.env`, LLM лимит $0.25 на основной прогон; отдельный финальный merge имеет собственный максимум $0.25, общий разрешённый пользователем бюджет $5):

```bash
.venv/bin/python scripts/run_all.py --llm-budget-usd 0.25 --sandbox-booking
```

Без `--llm-budget-usd` платные LLM-запросы не выполняются. `--sandbox-booking` включает только документированный LiteAPI sandbox-контроль с `sand_` ключом; production блокируется, реальные покупки запрещены. В текущем запуске prebook/book не дошли до вызова из-за отсутствия свежего тарифа. Сторонний MCP устанавливается из проверенного pinned commit в отдельную среду; установка требует доступа к GitHub/PyPI. Повторный прогон перезаписывает снимки результатов; цены и выдача могут измениться. Даты автоматически через 18 дней, 4 ночи, двое взрослых. Лимитированы размеры страниц и повторы; это не исчерпывающий обход поставщиков.

Проверки без сети и без расходов:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/run_all.py --reports-only
```

Для сравнения поведения LLM отдельно поддерживаются `--profile baseline`, `structured`, `orchestrated` в `scripts/run_llm_experiments.py --budget-usd 0.25`. Основной профиль orchestrated задаёт последовательность инструментов, поэтому не доказывает автономный выбор. Исторические baseline/structured прогоны сохранены; для их повторения запускать явно. Нет гарантий полного бюджета поездки: поисковые тарифы и кэш не равны подтверждённой оплате, неизвестные расходы не заменяются нулём.

Секреты не коммитить. Логи и JSON проходят редактирование секретов; отправляемые модели данные уже очищены. Полные исходные схемы MCP сохраняются для аудита, но не исполняются как инструкции. Тесты используют настоящие ответы, кроме явно отмеченного simulated timeout в LLM fallback.
