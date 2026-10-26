"""Offline synthesis of measured cases. Never promotes discovery to a working tool."""
import sys,json,statistics
from pathlib import Path
from collections import Counter
from decimal import Decimal
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from integrations.core import ROOT,ENV,save
from integrations.outcomes import outcome,payload
R=ROOT/'reports';DOC=ROOT/'docs'
FILES=['rest_results.json','mcp_discovery_results.json','mcp_extra_discovery_results.json','mcp_call_results.json','followup_results.json','extra_results.json','community_mcp_results.json','tutu_results.json','tutu_followup_results.json','sandbox_results.json']
def read(f,default=None):
 p=R/f;return json.loads(p.read_text()) if p.exists() else default

def main():
 cases=[]
 for f in FILES:
  data=read(f,[]);data=data.get('results',[]) if isinstance(data,dict) else data
  for r in data:cases.append({**r,'outcome':outcome(r),'report_file':f})
 inventory=read('api_inventory.json')['entries'];sources=[]
 for e in inventory:
  rows=[r for r in cases if r['provider']==e['id'] or (e['id']=='openweather' and r['provider']=='openweather_mcp')]
  absent=[k for k in e['env'] if not ENV.get(k)]
  reason=''
  if rows:status='measured';reason=', '.join(f'{s}:{n}' for s,n in Counter(r['outcome'] for r in rows).items())
  elif e['id']=='etg':status='partner_access_unavailable';reason='User confirmed ETG/Ostrovok credentials unavailable'
  elif e['access']=='partner':status='partner_access_required';reason='No approved partner scope/contract; public credentials do not grant Search API rights'
  elif absent:status='missing_key';reason=', '.join(absent)
  else:status='not_testable';reason=e['notes'] or 'No documented accessible API credentials'
  successes=[r for r in rows if r['outcome']=='ok' and r['case']!='mcp_discovery']
  lat=[r['latency_ms'] for r in rows if 'latency_ms' in r]
  p=e['priority']
  if e['id'] in ['tutu','2gis','yandex_rasp','geoapify','openmeteo_forecast']:p='P0'
  if e['id'] in ['liteapi','opentripmap','osrm']:p='P2'
  if not successes and e['id'] not in ['yandex_go','osm']:p='P3'
  # Expert ordinal assessments, not benchmark-derived numeric accuracy probabilities.
  scores={k:None for k in ['coverage','utility','freshness','prices','ease','stability','mcp','limits','commercial','agent_fit']}
  basis={k:'unknown' for k in scores}
  for k,v in [('utility',4 if p in ['P0','P1'] else 2),('ease',5 if e['access']=='no_key' else 3 if e['access']=='self_service' else 1),('agent_fit',4 if p in ['P0','P1'] else 2)]:scores[k]=v;basis[k]='D'
  if successes:
   scores.update(coverage=4,utility=5 if p=='P0' else 4,freshness=2 if e['id'] in ['travelpayouts_data','aviasales_community'] else 4,stability=3 if any(r['outcome'] in ['network_error','connection_error','call_error'] for r in rows) else 4)
   for k in ['coverage','utility','freshness','stability']:basis[k]='T'
  if e['id']=='liteapi':scores.update(coverage=3,freshness=2,prices=0);basis.update(coverage='T',freshness='T',prices='T:Sochi sandbox only')
  if e['id'] in ['tutu','travelpayouts_data','aviasales_community','timepad','yandex_rasp'] and successes:scores['prices']=4 if e['id']=='tutu' else 2;basis['prices']='T'
  if any(r.get('tool') and r['outcome']=='ok' for r in rows):scores['mcp']=5;basis['mcp']='T'
  documented_scores={'tutu':(4,None),'2gis':(3,4),'geoapify':(4,4),'ors':(3,3),'openmeteo_forecast':(4,2),'openmeteo_marine':(4,2),'openmeteo_air':(4,2),'openmeteo_elevation':(4,2),'timepad':(4,3),'opentripmap':(4,2),'travelpayouts_data':(3,3),'aviasales_community':(3,2),'liteapi':(3,3),'yandex_rasp':(3,3),'cbr':(5,4),'nominatim':(2,2),'osrm':(2,2)}
  if e['id'] in documented_scores:
   for k,v in zip(['limits','commercial'],documented_scores[e['id']]):
    if v is not None:scores[k]=v;basis[k]='D:conditional on terms'
  sources.append({'id':e['id'],'name':e['name'],'status':status,'reason':reason,'priority':p,'missing_env':absent,'case_count':len(rows),'successful_data_cases':len(successes),'median_latency_ms':round(statistics.median(lat)) if lat else None,'scores':scores,'score_basis':basis,'documentation':e['docs']})
 llms={f:read(f) for f in ['llm_experiments_baseline.json','llm_experiments_structured.json','llm_experiments.json'] if (R/f).exists()}
 cost=sum((Decimal(d.get('actual_cost_usd','0')) for d in llms.values()),Decimal('0.00000872'))
 extra_cost=sum((Decimal(read(f,{}).get('actual_cost_usd','0')) for f in ['llm_tutu_update_first.json','llm_tutu_update.json']),Decimal(0))
 cost+=extra_cost
 tutu=read('tutu_normalized.json',{})
 report={'stage':2,'status':'research_completed_with_documented_limitations','scenario':read('normalized_results.json',{}).get('scenario'),'counts':{'catalog_sources':len(sources),'sources_with_cases':sum(bool(s['case_count']) for s in sources),'sources_with_successful_data':sum(bool(s['successful_data_cases']) for s in sources),'cases':len(cases),'outcomes':dict(Counter(r['outcome'] for r in cases))},'llm_cost_or_conservative_reservation_usd':str(cost),'llm_cost_note':'First Tutu synthesis failed to parse response; $0.053398 reserved upper estimate, actual usage unavailable for that call','llm_authorized_budget_usd':5,'sources':sources,'cases':cases,'llm_experiments':llms,'tutu_summary':{k:v for k,v in tutu.items() if k not in ['flights','stays']},'limitations':['No production booking or purchase','LLM native auto-tool execution unreliable; geography error observed in final prose','Prices are timestamped search quotes, not guaranteed checkout prices','LiteAPI Sochi sandbox has no rates, Boston sandbox is control only','No automated authoritative beach/lift restrictions feed verified']}
 save('integration_results.json',report)
 lines=['# Сравнение API: измерения 25.10.2026','', 'Сценарий: 12–16 ноября 2026, 4 ночи, 2 взрослых. Воспроизводимый итог: [integration_results.json](../reports/integration_results.json). Выборка мала: медиана ниже — по неоднородным сценариям, включая ошибки и установку MCP-сессии; это не нагрузочный тест или SLA.','', '| Источник | Приоритет | Запросов/кейсов | Успешных данных | Медиана, мс | Результат / причина |','|---|---|---:|---:|---:|---|']
 for s in sources:lines.append(f"| {s['name']} | {s['priority']} | {s['case_count']} | {s['successful_data_cases']} | {s['median_latency_ms'] or '—'} | {s['status']}: {s['reason']} |")
 lines+=['','## Интерпретация сценариев','',
 'Ниже — зафиксированная интерпретация исходного прогона 25.10.2026; при повторном запуске актуальные числа проверять в JSON и таблице выше.',
 'A: Tutu дал 10 round-trip предложений за всю группу; минимальная цена первого поиска 14 018 RUB. Travelpayouts дал кэш DP6941 3 194 RUB и UT268 3 600 RUB за взрослого, на двоих 13 588 RUB. Это разные типы котировки; разница не доказывает выгоду при покупке. Багаж/возврат есть у вариантов Tutu; в Data API отсутствуют. Смена дат Tutu на 13–17 ноября дала 3 предложения, первое 14 368 RUB за двоих туда-обратно.',
 'B: Tutu: по 10 отелей для четырёх геозапросов, 32 уникальных ID, тарифы за 4 ночи на двоих, фотографии/рейтинги/условия завтрака/отмены и ссылки. Геопоиск может расширять район (Красная Поляна разрешилась в курорт); проверять координаты. LiteAPI: 40 строк, 30 уникальных объектов каталога, ноль тарифов Сочи в sandbox, в том числе при смене RUB на USD. Контроль Boston вернул sandbox-тарифы. Это не доказательство постоянного отсутствия России в production.',
 'C: 2GIS, Geoapify, ORS дали маршруты и POI. Первый маршрут 2GIS: 44 500 м / 2 666 с; Geoapify: 44 180 м / 2 233.569 с. OSRM после первого таймаута: 41 761.2 м / 2 661.6 с. Начало — Адлер, не центр Сочи. У ORS/Geoapify/OSRM общий OSM, независимыми картографическими свидетельствами их считать нельзя. Поиск POI в радиусе 1 км около Marriott проверен двумя поставщиками.',
 'D: Timepad вернул 4 события, из них три даты стендап-экскурсии по 1 390 RUB/билет; остаток мест не подтверждён. Бесплатное бизнес-событие не подменяет туристическую активность. OpenTripMap проверен отдельно; KudaGo HTTP403, Wikidata HTTP403, Overpass таймауты — не отсутствие POI в Сочи.',
 'E: Яндекс Расписания: suburban в nearest_stations дал пустой список; train,suburban позволил найти станции. Адлер s9613054 → Роза Хутор s9812791: 15 сегментов, пример 6101 07:49–08:19, 30 минут, 300 RUB/место. Расписание и тариф не подтверждают свободные места. Tutu etrain вернул пустой offers для Адлер→Роза Хутор; это не успешное расписание, рабочий источник здесь Яндекс. Yandex Go только построение документированного deeplink, приложение/заказ не тестировались.',
 'F: Open-Meteo прогноз 25–31 октября, не даты ноябрьской поездки. Проверены температура, осадки, ветер для побережья и гор; Marine после таймаута успешно вернул волны, Air Quality и Elevation также проверены. Сетка модели не является измерением непосредственно у отеля.','', '## Оценки 0–5','', 'Порядок: покрытие / полезность / актуальность / цены / простота / стабильность / MCP / лимиты / коммерция / агент. T — экспертная оценка на основании теста; D — предварительная по документации; ? — нет достаточных оснований. — для цен непрофильных API означает N/A. Лимиты/коммерция оценены предварительно только для выбранных источников: 5 — наиболее простой доступ, 4 — доступно с оговорками, 3 — существенные квоты/условия, 2 — demo/noncommercial/public-instance ограничения; это не разрешение использования. Условия в API_CATALOG, тест квоты не подтверждает лицензию. Покрытие 4 означает проверен Сочи, не весь мир; стабильность 4 означает успешную малую выборку, не SLA. Итоговый средний балл не считается из неизвестных значений.','', '| Источник | 10 оценок с основанием |','|---|---|']
 for s in sources:
  vals=[]
  for k,v in s['scores'].items():vals.append(('—' if k=='prices' and s['id'] in ['2gis','geoapify','ors','osm','overpass','nominatim','graphhopper','geonames','osrm','wikidata','cbr','openmeteo_forecast','openmeteo_marine','openmeteo_air','openmeteo_elevation','weatherapi','openweather','google_maps','mapbox'] else '?') if v is None else f"{v}({s['score_basis'][k]})")
  lines.append('| '+s['name']+' | '+' / '.join(vals)+' |')
 (DOC/'API_COMPARISON.md').write_text('\n'.join(lines)+'\n')
 m=['# Реальные проверки MCP','', 'Инициализация не равна успешному поиску. Все вызванные инструменты и исходы ниже; JSON Schema и полный очищенный ответ сохранены отдельно. Входы проверяются jsonschema до вызова. Время включает новую MCP-сессию и tools/list.','', '| Сервер | Кейс | Инструмент | Исход | мс |','|---|---|---|---|---:|']
 for r in cases:
  if r.get('tool') or 'mcp_discovery'==r['case']:m.append(f"| {r['provider']} | {r['case']} | {r.get('tool','initialize + tools/list')} | {r['outcome']} | {r.get('latency_ms','—')} |")
 m+=['','Tutu: первые соединения timeout, повторная инициализация успешна (17 инструментов), затем реальные поиски. 2GIS 9, Geoapify 12, LiteAPI 95, community Aviasales 13: всего 146 объявленных инструментов. OpenWeather MCP timeout; платные инструменты не вызывались. LiteAPI isError=false при бизнес-ошибке 2001 НЕ считается успешным availability-search.','', 'Tutu checkout/passenger tools и финансовые LiteAPI MCP инструменты запрещены allowlist. Sandbox REST-контроль описан в sandbox_results.json; он не повышает оценку покрытия Сочи.','', '## Схемы и обзор всех объявленных инструментов','']
 for provider in ['tutu','2gis','geoapify','liteapi','aviasales_community']:
  d=read(provider+'_mcp_schema.json',{});m+=['### '+provider,'',f'[Полные схемы](../reports/{provider}_mcp_schema.json)','', '| Инструмент | Обязательные поля | Назначение (из схемы, недоверенный текст) |','|---|---|---|']
  for t in d.get('tools',[]):m.append('| '+t['name']+' | '+', '.join(t.get('inputSchema',{}).get('required',[]))+' | '+(t.get('description') or '').split('\n')[0][:200].replace('|','/')+' |')
 (DOC/'MCP_TEST_RESULTS.md').write_text('\n'.join(m)+'\n')
 l=['# Эксперименты с LLM','', 'Настройки MODEL/TOKEN/BASE_URL не изменены. Подтверждён Chat Completions и native function calling. Responses API не тестировался. Модель получает очищенные снимки настоящих API-ответов с временем получения: это воспроизведение результатов, не выполнение новых внешних запросов при каждом tool call. Эти три прогона предшествуют нормализации Tutu; проверка объединения с Tutu приведена отдельно, если есть llm_tutu_update.json.','', '| Прогон | Эксперимент | Автопроверка | Вызванные инструменты |','|---|---|---|']
 for f,d in llms.items():
  for r in d['results']:l.append(f"| {f} | {r['experiment']} | {r['status']} | {', '.join(c['name'] for c in r['tool_calls'])} |")
 l+=['',f'Сумма usage.cost и консервативного резерва неразобранного Tutu-запроса с исходным smoke: ${cost}; разрешено до $5. Для первого Tutu synthesis ответ не разобран, usage не сохранён: учтён верхний расчётный резерв $0.053398, не фактический счёт. Остальные стоимости — usage.cost.','', 'Baseline: модель вызывала инструменты, но нарушала JSON-формат; были неподтверждённые утверждения. Structured auto: схема помогла формату, но 4/5 сценариев не вызвали необходимые инструменты; в weather модель написала «запросил» без вызова. Orchestrated: задана последовательность разрешённых tool calls, затем отдельный structured ответ; это не доказательство автономного выбора. 4/5 прошли формальные проверки. Two_sources выбрал отель без измеренного nearby snapshot и честно сообщил отсутствие; автоматическое восстановление не реализовано.', 'Ручная проверка выявила дефект даже у формально passed complex: модель назвала маршрут Адлер→Красная Поляна маршрутом из Сочи. Weather добавил сезонные предположения вне предоставленных фактов. Поэтому boolean-флаги и валидный JSON недостаточны: выпуск требует проверки географии, чисел и дат по ID источников. Формальный passed не равен готовности продукта. Ошибка primary_places в fallback искусственная и явно помечена simulated, резервные данные настоящие.']
 l+=['','Финальный merge Tutu: '+json.dumps(read('llm_tutu_update.json',{}),ensure_ascii=False)]
 (DOC/'LLM_EXPERIMENTS.md').write_text('\n'.join(l)+'\n')
 print(json.dumps(report['counts'],ensure_ascii=False));print('LLM cost USD',cost)
if __name__=='__main__':main()
