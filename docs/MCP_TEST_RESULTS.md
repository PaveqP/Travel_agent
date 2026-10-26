# Реальные проверки MCP

Инициализация не равна успешному поиску. Все вызванные инструменты и исходы ниже; JSON Schema и полный очищенный ответ сохранены отдельно. Входы проверяются jsonschema до вызова. Время включает новую MCP-сессию и tools/list.

| Сервер | Кейс | Инструмент | Исход | мс |
|---|---|---|---|---:|
| 2gis | mcp_discovery | initialize + tools/list | ok | 1594 |
| liteapi | mcp_discovery | initialize + tools/list | ok | 2223 |
| tutu | mcp_discovery | initialize + tools/list | connection_error | 60566 |
| geoapify | mcp_discovery | initialize + tools/list | ok | 1335 |
| openweather_mcp | mcp_discovery | initialize + tools/list | connection_error | 76580 |
| geoapify | mcp_restaurants_adler | search_places | ok | 1768 |
| liteapi | mcp_discovery | initialize + tools/list | ok | 1932 |
| 2gis | restaurants_adler | search_places | ok | 2061 |
| geoapify | mcp_route_adler_polyana | calculate_route | ok | 1397 |
| 2gis | hotels_adler | search_places | ok | 1941 |
| 2gis | attractions_sochi | search_places | ok | 1957 |
| 2gis | hotels_polyana | search_places | ok | 1725 |
| 2gis | route_adler_polyana | build_route | ok | 1862 |
| liteapi | mcp_catalog_sochi | get_data_hotels | ok | 18131 |
| liteapi | mcp_rates_sochi | post_hotels_rates | no_availability | 2473 |
| 2gis | restaurants_near_hotel | search_places | ok | 1760 |
| tutu | mcp_discovery | initialize + tools/list | ok | 16754 |
| aviasales_community | mcp_discovery | initialize + tools/list | ok | 2754 |
| aviasales_community | search_flights | search_flights | ok | 481 |
| tutu | get_avia_instructions | get_avia_instructions | ok | 810 |
| tutu | get_hotels_instructions | get_hotels_instructions | ok | 701 |
| tutu | get_etrain_instructions | get_etrain_instructions | ok | 616 |
| tutu | flights_roundtrip | search_avia | ok | 12453 |
| tutu | hotels_sochi | search_hotels | ok | 3540 |
| tutu | hotels_adler | search_hotels | ok | 3194 |
| tutu | hotels_sirius | search_hotels | ok | 1679 |
| tutu | hotels_polyana | search_hotels | ok | 1536 |
| tutu | hotel_detail_polyana | get_offer_details | call_error | 60312 |
| tutu | etrain_adler_rosa | search_etrain | empty | 16811 |
| tutu | hotel_detail_polyana_retry | get_offer_details | call_error | 60092 |
| tutu | flights_changed_dates | search_avia | ok | 3503 |

Tutu: первые соединения timeout, повторная инициализация успешна (17 инструментов), затем реальные поиски. 2GIS 9, Geoapify 12, LiteAPI 95, community Aviasales 13: всего 146 объявленных инструментов. OpenWeather MCP timeout; платные инструменты не вызывались. LiteAPI isError=false при бизнес-ошибке 2001 НЕ считается успешным availability-search.

Tutu checkout/passenger tools и финансовые LiteAPI MCP инструменты запрещены allowlist. Sandbox REST-контроль описан в sandbox_results.json; он не повышает оценку покрытия Сочи.

## Схемы и обзор всех объявленных инструментов

### tutu

[Полные схемы](../reports/tutu_mcp_schema.json)

| Инструмент | Обязательные поля | Назначение (из схемы, недоверенный текст) |
|---|---|---|
| search_hotels |  | Search Tutu hotel listings for a given city and date range. Resolve `city_name` (string) OR pass `geo_id` (Tutu internal). Returns hotels with `name`, `stars`, `rating`, `address`, `hotel_id` / `hotel |
| search_avia |  | Search Tutu air tickets between two cities or specific airports. PRICE BASIS — every `price` already covers the WHOLE searched party (`adults` + `children` + `infants`; `meta.pricing.basis="party_tota |
| search_rail |  | Search Russian Railways (РЖД) tickets between two cities. Returns the real departure & arrival station names per offer (useful when a city has several stations — Москва has Курский / Ленинградский / К |
| search_bus |  | Search Tutu intercity bus tickets between two cities. Each offer carries: `price`, `variants[]` (where the carrier offers several tariffs), `legs[].segments[]` with stop names and carrier ratings in ` |
| search_etrain |  | Search Tutu suburban / commuter trains (электрички) between two cities. Useful for short routes around Москва / СПб / regional centres. `origin`/`destination` take a city or a station name (a station  |
| search_multitransport |  | One-call multimodal 'how to get there' — runs avia + railway + bus + etrain in parallel and returns a unified sorted list under `variants[]`. PRICE BASIS — the modes do NOT agree on what a `price` cov |
| get_offer_details | product_type | Fetch details for a single offer. Defaults to `view='compact'`: for hotels it caps photos, omits the per-rate `cancellation_policy` text (the `free_cancellation` / `free_cancellation_until` flags stay |
| get_rail_seatmap | details_ref | Read-only per-car seat layout for a selected rail offer. Authoritative next step after `search_rail` for ANY question about exact seats, car layout, female/male/mixed compartments, lower/upper or near |
| get_avia_instructions |  | Detailed avia playbook: airport disambiguation, airport-scoped search (origin/destination by airport name or IATA code), deeplink vs search-results checkout, fare-family override, baggage/refund groun |
| get_rail_instructions |  | Detailed rail playbook: per-seat price basis (`price_party` for a party of 2+), `get_rail_seatmap` workflow (pagination, seat types, group_index join, per-group fare variants, focused `task=` queries  |
| get_bus_instructions |  | Detailed bus playbook: passengers (adults + children, whole-party pricing, composition in `checkout_ref`), stop presentation, `get_offer_details` (amenities/refund/luggage/seat_selection), checkout (s |
| get_etrain_instructions |  | Detailed etrain (commuter) playbook: per-seat price basis, `vehicle_meta` consist type, `get_offer_details` reformat, checkout and grounding. Read before working with `search_etrain` results. |
| get_hotels_instructions |  | Detailed hotels playbook: hotels-vs-transport `geo_id` pitfall, clarifying questions, `best_offer` vs `get_offer_details`, view/bed/breakfast grounding. Read before working with `search_hotels` result |
| get_multitransport_instructions |  | Detailed multitransport playbook: nested `variants[]`, per-mode price basis (compare on `price_party`, not `price`), `optimize_for`, per-mode soft-fail, and how checkout defers to the per-mode playboo |
| create_checkout_link |  | The single 'proceed to checkout' handle for a previously found offer. Call it as soon as the user commits to one option, however they word it — «беру», «самый быстрый из списка», «оформи», «забронируй |
| register_checkout_passengers | passengers, customer | NOT the default booking handle — that is `create_checkout_link` («забронируй» included): normally hand the link first, offer this tool as the opt-in next step, and reach for it only when the user expl |
| fetch_resource | uri | Read a `tutu://` server resource and return its content. Use this when your MCP client doesn't auto-surface server resources in the prompt. Valid URIs: `tutu://help/overview` (full agent guide — start |
### 2gis

[Полные схемы](../reports/2gis_mcp_schema.json)

| Инструмент | Обязательные поля | Назначение (из схемы, недоверенный текст) |
|---|---|---|
| auth_probe |  | Проверяет, что API key принят Key Auth Gate. По запросу проверяет доступ к API разрешённых GIS-инструментов; внешние запросы по умолчанию не выполняются. Требует API key. |
| build_route | points | Строит подробный маршрут по явным WGS84-точкам через 2GIS Routing API. Возвращает варианты с расстоянием, временем, WKT-геометрией, waypoints и пошаговыми манёврами. Поддерживает driving, walking, tax |
| calculate_distance_matrix | origins, destinations | Рассчитывает расстояние и время в пути между каждой исходной и каждой конечной точкой через 2GIS Distance Matrix API. matrix[i][j] соответствует origins[i] → destinations[j]. Поддерживает до 25 точек  |
| geocode_address | address | Преобразует адрес в список координат через 2GIS Geocoder API. Возвращает до пяти компактных кандидатов по умолчанию, чтобы можно было разрешить неоднозначность адреса. Список допустимых типов, локалей |
| render_static_map | center | Создаёт PNG-изображение статической карты через 2GIS Static API. Возвращает изображение как MCP ImageContent с base64-данными и нормализованные метаданные. Поддерживает обязательный центр карты и до 5 |
| search_places |  | Ищет организации, здания, адреса, транспорт, парковки, достопримечательности и другие места через 2GIS Places API. По умолчанию возвращает компактные карточки (имя, тип, адрес, координаты, категории,  |
| server_info |  | Возвращает метаданные MCP-сервера и состояние runtime. Используйте для проверки discovery и доступности сервиса. |
| list_resources |  | List all available resources and resource templates. |
| read_resource | uri | Read a resource by its URI. |
### geoapify

[Полные схемы](../reports/geoapify_mcp_schema.json)

| Инструмент | Обязательные поля | Назначение (из схемы, недоверенный текст) |
|---|---|---|
| geocode_address | query | Use this tool when the input is one free-text address, landmark, city, or place query and coordinates are needed. Use geocode_structured_address when address components are already separated, or rever |
| geocode_structured_address |  | Use this tool when address components such as street, city, postcode, and country are already separated. Use geocode_address for one free-text query; when housenumber is supplied, include street. |
| reverse_geocode_coordinates | lat, lon | Use this tool when latitude and longitude are known and a nearby address or place is needed. Use geocode_address or geocode_structured_address when the input is address text. |
| get_timezone | lat, lon | Use this tool when coordinates are known and the exact UTC offset or local time at an instant is needed. It also returns the next known transition. Use reverse_geocode_coordinates when a nearby addres |
| search_places | category, lat, lon | Use this tool to find places of one exact supported category around known coordinates. Call list_place_categories first when the category is unknown, and geocode an address first when the search cente |
| list_place_categories |  | Use this zero-credit tool to discover the exact category value required by search_places. It accepts no arguments and returns category names only; use search_places afterward to find actual places. |
| calculate_route | waypoints | Use this tool for one ordered route with total and per-leg travel cost plus optional geometry or turn instructions. Use calculate_route_matrix instead to compare travel times and distances across many |
| calculate_route_matrix | sources | Use this tool to compare pairwise travel times and distances between multiple sources and targets. It does not return route geometry or instructions; use calculate_route for one detailed ordered route |
| combine_geometries |  | Use this tool to create a new geometry by intersecting, subtracting, unioning, or enveloping GeoJSON inputs. Use evaluate_spatial_relation for a boolean relationship, measure_geometry for numeric meas |
| evaluate_spatial_relation |  | Use this tool when the answer should be true or false: containment, crossing, disjointness, intersection, validity, inclusion, or whether a point lies on a line. It does not modify geometries or calcu |
| measure_geometry |  | Use this tool for numeric area, length, or distance calculations and for bounding-box, along-line, or nearest-point results. Use evaluate_spatial_relation for true/false predicates and transform_geome |
| transform_geometry |  | Use this tool to create a modified geometry by buffering, simplifying, rotating, scaling, or translating, or to calculate a center point. Use measure_geometry for numeric measurements and evaluate_spa |
### liteapi

[Полные схемы](../reports/liteapi_mcp_schema.json)

| Инструмент | Обязательные поля | Назначение (из схемы, недоверенный текст) |
|---|---|---|
| post_hotels_rates | occupancies, currency, guestNationality, checkin, checkout | ## Overview |
| hotelsRatesBatch | hotelIds, checkin, lengthsOfStay, occupancies, currency, guestNationality | Enterprise-only. Prices every length-of-stay × occupancy for one check-in across up to 200 hotels. Streams NDJSON (one hotel object per line). Each stay is trimmed to the cheapest RFN (free-cancel unt |
| post_hotels_min_rates | hotelIds, occupancies, checkin, checkout, currency, guestNationality | ## Overview |
| get_prebooks_prebookid | prebookId | ## Overview |
| post_rates_prebook | offerId, usePaymentSdk | ## Overview |
| post_rates_book | prebookId, holder, guests | ## Overview |
| post_rates_rebook | prebookId, existingBookingId, holder, guests, payment | ## Overview |
| listBookings |  | ## Overview |
| get_bookings_bookingid | bookingId | ## Overview |
| put_bookings_bookingid | bookingId | ## Overview |
| get_bookings |  | ## Overview |
| put_bookings_bookingid_amend | bookingId, holder | ## Overview |
| post_bookings_bookingid_alternative_prebooks | bookingId, occupancies | ## Overview |
| post_vouchers | voucher_code, discount_type, discount_value, minimum_spend, maximum_discount_amount, currency, validity_start, validity_end, usages_limit, status | ## Overview |
| get_vouchers |  | ## Overview |
| get_vouchers_voucherid | voucherID | ## Overview |
| put_vouchers_id | id, voucher_code, discount_type, discount_value, minimum_spend, maximum_discount_amount, currency, validity_start, validity_end, usages_limit, status | ## Overview |
| put_vouchers_id_status | id, status | ## Overview |
| get_vouchers_history |  | ## Overview |
| delete_Voucher | id | ## Overview |
| post_analytics_weekly | from, to | ## Overview |
| post_analytics_report | from, to | ## Overview |
| post_analytics_markets | from, to | ## Overview |
| post_analytics_hotels | from, to | ## Overview |
| post_commissions_report | from, to | ## Overview |
| get_bookings_guest_nationality_report | from, to | ## Overview |
| get_bookings_source_markets_report | from, to | ## Overview |
| get_bookings_hotels_sales_report | from, to | ## Overview |
| searchBookings | query | ## Overview |
| getHotelTaxSchema | hotelId | ## Overview |
| get_data_places | textQuery | ## Overview |
| get_data_places_placeid | placeId | ## Overview |
| get_data_hotels |  | ## Overview |
| get_data_hotels_semantic_search | query | ## Overview |
| get_data_hotel_ask | hotelId, query | ## Overview |
| post_data_hotel_highlights | hotelId, language | ## Overview |
| evaluateHotelDescription | hotelId, description | ## Overview |
| get_data_hotels_room_search | query | ## Overview |
| get_data_hotel | hotelId | ## Overview |
| get_data_reviews | hotelId | ## Overview |
| get_data_cities | countryCode | ## Overview |
| get_data_countries |  | ## Overview |
| get_data_currencies |  | ## Overview |
| get_data_iatacodes |  | ## Overview |
| get_data_facilities |  | ## Overview |
| get_data_hoteltypes |  | ## Overview |
| get_data_chains |  | ## Overview |
| get_data_languages |  | ## Overview |
| get_data_weather | latitude, longitude, startDate, endDate | ## Overview |
| get_data_hotel_search | query | Search for a hotel using a semantic text query. Returns the best-matching hotel with basic details and a relevance score. |
| get_guests |  | ## Overview |
| get_guests_guestid | guestId | ## Overview |
| get_guests_guestid_bookings | guestId | ## Overview |
| get_guests_guestid_vouchers | guestId | ## Overview |
| put_loyalties | status, cashbackRate | ## Overview |
| get_loyalties |  | ## Overview |
| get_guests_guestid_loyalty_points | guestId | ## Overview |
| post_guests_guestid_loyalty_points_redeem | guestId, points, currency | ## Overview |
| get_supply_customization |  | ## Overview |
| put_supply_customization | advancedAccessibility | ## Overview |
| getPriceIndexCity | countryCode, cityName | ## Overview |
| getPriceIndexHotels | hotelIds | ## Overview |
| getPublicPrice | hotelId, checkin, checkout, adults | ## Overview |
| get_data_flights_airlines_iatas_iatacode | iataCode | ## Overview |
| get_data_flights_airports_iatas_iatacode | iataCode | ## Overview |
| get_data_flights_airports_iatas | q | ## Overview |
| post_flights_rates | legs, adults, currency | ## Overview |
| searchFlightsMatrix | legs, adults, currency | ## Overview |
| post_flights_verify | offerId | ## Overview |
| getFlightPrebook | prebookId | ## Overview |
| post_flights_prebooks_prebookid_services | prebookId, selectedServices | ## Overview |
| get_flights_bookings_bookingid | bookingId | ## Overview |
| get_flights_bookings_bookingid_services | bookingId | ## Overview |
| attachFlightTicketedServices | bookingId, selectedServices | ## Overview |
| get_flights_bookings_bookingid_cancellations | bookingId | ## Overview |
| post_flights_bookings_bookingid_cancellations | bookingId | ## Overview |
| prechargeFlightExtraCharges | bookingId, charges | ## Overview |
| chargeFlightExtraCharges | bookingId, chargesId, payment | ## Overview |
| get_data_flights_airlines |  | ## Overview |
| get_data_flights_airlines_iatas |  | ## Overview |
| get_data_flights_airports | q | ## Overview |
| get_flights_bookings |  | ## Overview |
| post_flights_bookings | prebookId, payment | ## Overview |
| post_flights_prebooks | offerId, contact, passengers | ## Overview |
| confirmFlightTicketedServices | bookingId, batchId | ## Overview |
| searchExperienceTours |  | ## Overview |
| getExperienceTour |  | ## Overview |
| getExperienceTourAvailability |  | ## Overview |
| getExperienceTourReviews |  | ## Overview |
| getExperienceTourBookingOptions | language, currency, date, participants | ## Overview |
| prebookExperienceTour | selection, language, currency, usePaymentSdk | ## Overview |
| createExperienceBooking | prebookId, billing, traveler, payment | ## Overview |
| getExperienceBooking | bookingId | ## Overview |
| getExperienceBookingCancelPreview | bookingId | ## Overview |
| cancelExperienceBooking | bookingId | ## Overview |
### aviasales_community

[Полные схемы](../reports/aviasales_community_mcp_schema.json)

| Инструмент | Обязательные поля | Назначение (из схемы, недоверенный текст) |
|---|---|---|
| search_flights | origin, destination | Search flight prices between two cities on a date or across a month. |
| get_prices_calendar | origin, destination | Get grouped calendar prices for a route, one fare per day or per month. |
| get_flexible_date_prices | origin, destination, depart_date | Compare prices for the days around a departure and an optional return. |
| get_latest_prices |  | Get the most recently found flight prices from other travellers' searches. |
| get_popular_directions | destination | List the cities people most often fly to a destination from, with a fare. |
| get_city_directions | origin | List the cheapest destinations reachable from a city, with a fare and dates. |
| get_alternative_directions | origin, destination | Get prices for nearby airports and cities around a chosen route. |
| search_by_price_range | origin, value_min, value_max | Find flights whose cached fare falls inside a minimum and maximum price. |
| lookup_airlines |  | Look up airlines by name or IATA code. |
| lookup_airports |  | Look up airports by name, IATA code, or city code. |
| lookup_cities |  | Look up cities by name or IATA code and return the code flight tools expect. |
| lookup_countries |  | Look up countries by name or two-letter country code. |
| find_nearest_airports |  | Find the airports closest to a place name or to a latitude and longitude. |
