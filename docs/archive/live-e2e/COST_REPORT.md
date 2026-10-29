# Общий бюджет повторного live-прогона

Максимум $5 на все пять кейсов и диагностику. Soft stop $4.50, резерв $0.50. Предыдущий blocked запуск расходовал $0. Текущий единый ledger: accounted **$4.4679709808**, pending **$0**. Достоверно возвращённая LLM стоимость **$0.1427329808**. API учтены консервативными резервами; точного счёта их аккаунтов нет. Платные подписки/пакеты и реальные покупки не оформлялись.

Модель `deepseek/deepseek-v4.1-flash-1017`, прежний BASE_URL OpenRouter без изменений. До первого inference публичные `/models` и `/models/{model}/endpoints` дали HTTP 200, metadata `/key` HTTP 200. Лимит ключа не задан, поэтому полагаться на него нельзя. Максимальные найденные тарифы среди endpoints с overrides: input $0.45/M и output $1.80/M. Guard использует ещё более высокий $2/M для каждого byte входного JSON + 8192 единиц запаса и max_tokens выхода; cached discount заранее не учитывается. max_tokens/stream/model проверяются до сети; SDK retries=0.

Guard установлен только тестовым launcher в общий AsyncClient.send, включая отдельные MCP clients. Атомарное резервирование в одном event loop происходит до await/отправки; spent + pending + новый reserve <= $4.50. После ответа списывается usage.cost, иначе полный резерв, включая timeout/cancellation; счётчик пережил restart через --resume-budget без сброса расходов. Покрыт пятью offline-тестами: общий pending, освобождение неизрасходованного резерва, timeout, предел, redaction. Unknown hosts блокируются до сети.

| Категория | Операций учёта | Provider-reported USD | Учтено USD | Политика |
|---|---:|---:|---:|---|
| 2gis | 257 | N/A | 2.95 | $0.05 на каждый tools/call, включая отменённый; prepaid/demo квота, без покупки лимитов |
| geoapify | 14 | N/A | 0.14 | $0.01 за чтение <=10 POI, консервативная аллокация квоты |
| llm | 145 | 0.1427329808 | 1.3349709808 | usage.cost; при неполном биллинге весь request reserve |
| openmeteo | 9 | N/A | 0.009 | $0.001 за чтение публичного/квотного API, без upgrade |
| opentripmap | 5 | N/A | 0.005 | $0.001 за чтение публичного/квотного API, без upgrade |
| tavily | 1 | N/A | 0.016 | до $0.016 на search/extract, worst 2 credits × $0.008 |
| timepad | 9 | N/A | 0.009 | $0.001 за чтение публичного/квотного API, без upgrade |
| travelpayouts | 4 | N/A | 0.004 | $0.001 за чтение публичного/квотного API, без upgrade |
| tutu | 364 | N/A | 0 | публичный read-only без платёжного аккаунта, $0; handshake тоже учтён |

Операции учёта включают нулевые MCP handshake/list/notification/GET — не путать их с числом бизнес-вызовов. Резервы API намеренно не возвращаются как «бесплатные»: план конкретного аккаунта не измерен; использовались только существующие чтения, без покупки подписок/лимитов. 2ГИС документирует ограничение доступа при исчерпании пакета; Geoapify предлагает upgrade, а не автоматическую покупку. $0.50 остаётся на неизвестный/запаздывающий биллинг. Это консервативный бюджетный учёт, а не утверждение об exact долларовой цене квоты.

Input 1228864, completion 113902, cached input 394112. Токены показаны только по доступному usage; при timeout они неизвестны, а стоимость целиком зарезервирована. Ни скрытые рассуждения, ни сырой LLM output не сохранялись. Диагностические повторные пользовательские сообщения видны в conversation.json, никакого скрытого полного replay успешных сценариев.

Источники тарифов: [OpenRouter models API](https://openrouter.ai/api/v1/models), [endpoints модели](https://openrouter.ai/api/v1/models/deepseek/deepseek-v4.1-flash-1017/endpoints), [Tavily credits](https://docs.tavily.com/documentation/api-credits), [2ГИС billing/limits](https://docs.2gis.com/en/platform-manager/subscription/pricing), [Geoapify pricing](https://www.geoapify.com/pricing/), [Яндекс Расписания](https://yandex.ru/dev/rasp/raspapi), [Open-Meteo](https://github.com/open-meteo/open-meteo).
