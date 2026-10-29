import { test } from "node:test";
import assert from "node:assert/strict";
import {
  money,
  safeUrl,
  tripStatus,
  currentOption,
  tripParts,
  tripMapPoints,
  tripMapUrls,
  canCheckout,
  feedbackText,
  messageLinks,
  transportRoutes,
  offerItems,
  offerChoice,
  offerSelected,
  counted,
  sortByPrice,
} from "./format.js";

test("price ranking keeps unknown costs last, preserves ties and does not mutate agent order", () => {
  const items = [
    { id: "unknown" }, { id: "paid", price: { amount: "100", currency: "RUB" } },
    { id: "free", price: { amount: "0", currency: "RUB" } },
    { id: "same", price: { amount: "100", currency: "RUB" } },
    { id: "missing", price: { amount: null } },
  ];
  assert.deepEqual(sortByPrice(items, "asc").map((item) => item.id), ["free", "paid", "same", "unknown", "missing"]);
  assert.deepEqual(sortByPrice(items, "desc").map((item) => item.id), ["paid", "same", "free", "unknown", "missing"]);
  assert.equal(sortByPrice(items, ""), items);
  assert.equal(items[0].id, "unknown");
});

test("panel merges matching evidence with cards and selects only current permitted choices", () => {
  const hotel = { id: "h", role: "stays", name: "Отель", url: "https://example.org/h", price: {amount:"100",currency:"RUB",basis:"room_stay"} };
  const state = { stage: "review", revision: 2, results: {stays:{candidates:[hotel]}}, cards:[{id:"h",kind:"stays",title:"Отель",selectable:true}], options:[{id:"package",revision:2,stay:hotel,transport:{id:"t"}}],choices:[{id:"package"}],selected:null };
  assert.equal(offerItems(state,"stays").length,1);
  assert.equal(offerItems(state,"stays")[0].url,hotel.url);
  assert.equal(offerChoice(state,hotel,"stays"),"package");
  assert.equal(offerSelected(state,hotel,"stays"),false);
  assert.equal(offerSelected({...state,selected:"package"},hotel,"stays"),true);
  assert.equal(offerChoice({...state,revision:3},hotel,"stays"),null);
  assert.equal(offerChoice({...state,stage:"booked"},hotel,"stays"),null);
  assert.equal(offerChoice({...state,cards:[{id:"h",selectable:false}]},hotel,"stays"),null);
});

test("chat links preserve labels, punctuation, query strings and safe protocols", () => {
  const parts = messageLinks("См. [отель](https://hotel.tutu.ru/details?id=1&adults=2) и https://example.org/view_(sea). Потом https://tutu.ru.");
  assert.deepEqual(parts.filter((part) => part.href), [
    { text: "отель", href: "https://hotel.tutu.ru/details?id=1&adults=2" },
    { text: "https://example.org/view_(sea)", href: "https://example.org/view_(sea)" },
    { text: "https://tutu.ru", href: "https://tutu.ru/" },
  ]);
  assert.equal(parts.at(-1).text, ".");
  assert.equal(messageLinks("[клик](javascript:alert(1)) <script>код</script>").some((part) => part.href), false);
  assert.equal(messageLinks("https://secret:password@example.org").some((part) => part.href), false);
  assert.equal(messageLinks("[Первый](https://one.example) [Второй](https://two.example)").filter((part) => part.href).length, 2);
});

test("return tickets use their own airports, carrier and arrival instead of outbound details", () => {
  const outbound = { origin: "SVO", destination: "AER", departure_at: "2026-11-12T11:30:00+03:00", arrival_at: "2026-11-12T15:20:00+03:00" };
  const returning = { origin: "AER", destination: "VKO", departure_at: "2026-11-16T15:10:00+03:00", arrival_at: "2026-11-16T19:00:00+03:00", carriers: ["Utair"], flight_numbers: ["UT-268"] };
  assert.deepEqual(transportRoutes({ legs: [outbound, returning] }), [outbound, returning]);
  const legacy = transportRoutes({ origin: "Москва", destination: "Сочи", duration_minutes: 230, transfers: 0, return_departure_at: returning.departure_at, end: "2026-11-16" });
  assert.equal(legacy[1].origin, "Сочи");
  assert.equal(legacy[1].destination, "Москва");
  assert.equal(legacy[1].departure_at, returning.departure_at);
  assert.equal(legacy[1].arrival_at, undefined);
  assert.equal(legacy[1].duration_minutes, undefined);
  assert.equal(legacy[1].transfers, undefined);
  assert.equal(transportRoutes({ legs: [outbound], return_departure_at: returning.departure_at })[1].departure_at, returning.departure_at);
});

test("unknown costs are distinct from zero", () => {
  assert.equal(money(null), "Уточняется");
  assert.match(money(0), /0/);
});

test("autonomous status distinguishes packages, hotel search and incomplete plans", () => {
  assert.equal(
    tripStatus({ autonomous: true, options: [{ id: "a" }] }),
    "Варианты готовы",
  );
  assert.equal(
    tripStatus({ autonomous: true, options: [], status: "partial" }),
    "План требует уточнений",
  );
  assert.equal(
    tripStatus({ autonomous: true, selected: "a", options: [{ id: "a" }], status: "partial" }),
    "План требует уточнений",
  );
  assert.equal(
    tripStatus({ autonomous: true, focus: "stays", cards: [{ id: "hotel" }] }),
    "Отели найдены",
  );
  assert.equal(
    tripStatus({ autonomous: true, selected: "a" }),
    "Вариант выбран",
  );
});

test("checkout requires an explicitly selected current package with fresh live quotes", () => {
  const now = Date.parse("2026-11-01T10:00:00Z");
  const candidate = {
    price: { amount: "10000" },
    source: { evidence: "live", expires_at: "2026-11-01T10:10:00Z" },
  };
  const option = {
    id: "a",
    revision: 2,
    transport: candidate,
    stay: candidate,
  };
  const state = {
    autonomous: true,
    stage: "review",
    revision: 2,
    selected: "a",
    options: [option],
  };
  assert.equal(canCheckout(state, now), true);
  for (const change of [
    { selected: null },
    { selected: "missing" },
    { revision: 3 },
    { stage: "booked" },
    { options: [{ ...option, stay: null }] },
    {
      options: [
        {
          ...option,
          stay: {
            ...candidate,
            source: { ...candidate.source, evidence: "catalog" },
          },
        },
      ],
    },
  ])
    assert.equal(canCheckout({ ...state, ...change }, now), false);
  assert.equal(canCheckout(state, now + 11 * 60 * 1000), false);
  assert.equal(canCheckout(null, now), false);
});

test("planning feedback has a user-facing explanation without exposing internal tasks", () => {
  assert.match(feedbackText({ code: "arrival_stay_mismatch" }), /даты отеля/);
  assert.match(feedbackText({ code: "no_transport" }), /билеты/);
  assert.equal(
    feedbackText({ code: "new_code", detail: "internal task" }),
    "Часть поездки требует уточнения с агентом.",
  );
});
test("provider links cannot execute scripts or carry credentials", () => {
  for (const url of [
    "javascript:alert(1)",
    "data:text/html,a",
    "https://secret:password@example.org",
  ])
    assert.equal(safeUrl(url), null);
  assert.equal(safeUrl("https://tutu.ru"), "https://tutu.ru/");
});
test("tracking uses booking and calendar dates", () => {
  const s = {
    stage: "booked",
    constraints: { start: "2026-12-01", end: "2026-12-05" },
  };
  assert.equal(tripStatus(s, "2026-11-01"), "Скоро в путь");
  assert.equal(tripStatus(s, "2026-12-03"), "В путешествии");
  assert.equal(tripStatus(s, "2026-12-06"), "Воспоминания");
  assert.equal(
    tripStatus({ ...s, stage: "review" }, "2026-12-03"),
    "Планируем",
  );
});
test("summary follows selected option", () => {
  assert.equal(
    currentOption({ selected: "b", options: [{ id: "a" }, { id: "b" }] }).id,
    "b",
  );
});

test("party labels preserve children and infant ages", async () => {
  const { party } = await import("./format.js");
  assert.equal(party(2, [6, 1]), "2 взрослых; дети (возраст): 6, 1");
  assert.equal(party(1, []), "1 взрослый");
  assert.equal(counted(1, "день", "дня", "дней"), "1 день");
  assert.equal(counted(2, "вариант", "варианта", "вариантов"), "2 варианта");
  assert.equal(counted(14, "день", "дня", "дней"), "14 дней");
});

test("saved trip parts follow selected IDs before a complete option exists", () => {
  const transport = { id: "flight", name: "Выбранный рейс" };
  const stay = { id: "hotel", name: "Выбранный отель" };
  const state = {
    selected_transport: "flight",
    selected_stay: "hotel",
    results: {
      transport: { candidates: [{ id: "other" }, transport] },
      stays: { candidates: [stay] },
    },
  };
  assert.equal(tripParts(state).transport, transport);
  assert.equal(tripParts(state).stay, stay);
  assert.equal(tripParts({ ...state, selected_stay: null }).stay, undefined);
  assert.equal(tripParts(state).total, undefined);
});

test("booked map and artifacts use the original order snapshot", () => {
  const state = {
    stage: "booked",
    options: [
      {
        stay: { name: "Новый вариант" },
        budget: { known_subtotal: "90000" },
        days: [],
      },
    ],
    receipt: {
      items: [
        {
          kind: "stays",
          name: "Сохранённый отель",
          details: { area: "Сириус", coordinates: { lat: 43.4, lon: 39.98 } },
        },
      ],
      payment: { amount: "80000" },
      itinerary: [],
    },
  };
  assert.equal(tripParts(state).stay.name, "Сохранённый отель");
  assert.equal(tripParts(state).total, "80000");
  assert.equal(tripMapPoints(state)[0].approximate, false);
  assert.equal(
    tripParts({ ...state, stage: "review" }).stay.name,
    "Новый вариант",
  );
});

test("map distinguishes exact coordinates, district markers and unknown locations", () => {
  const exact = {
    id: "exact",
    name: "Парк",
    area: "Сочи",
    coordinates: { lat: 43.5, lon: 39.9 },
  };
  const state = {
    options: [
      {
        transport: { id: "train", name: "Поезд", destination: "Адлер" },
        stay: { id: "stay", name: "Отель", area: "Сириус" },
        days: [
          {
            candidates: [
              exact,
              { id: "unknown", name: "Место без адреса" },
              { id: "outside", coordinates: { lat: 55.75, lon: 37.62 } },
            ],
          },
          { candidates: [exact] },
        ],
      },
    ],
  };
  const points = tripMapPoints(state);
  assert.equal(points.length, 4);
  assert.equal(points[0].kind, "transport");
  assert.equal(points[1].approximate, true);
  assert.equal(points[1].area, "Сириус");
  assert.equal(points[2].approximate, false);
  assert.equal(points[2].lon, 39.9);
  assert.equal(points[2].lat, 43.5);
  assert.equal(points[3].lon, 37.62);
  assert.equal(points[3].lat, 55.75);
  assert.deepEqual(tripMapPoints(null), []);
});

test("map embeds all trip points and opens the same points in Yandex Maps", () => {
  const points = [
    { id: "hotel", lon: 39.72, lat: 43.59, approximate: false },
    { id: "mountains", lon: 40.27, lat: 43.67, approximate: false },
  ];
  const urls = tripMapUrls(points);
  const embed = new URL(urls.embed), external = new URL(urls.external);
  assert.equal(embed.origin, "https://yandex.ru");
  assert.equal(embed.pathname, "/map-widget/v1/");
  assert.equal(embed.searchParams.get("pt"), "39.72,43.59~40.27,43.67");
  assert.equal(external.pathname, "/maps/");
  assert.equal(embed.search, external.search);
  const [[west, south], [east, north]] = embed.searchParams.get("bbox").split("~").map((pair) => pair.split(",").map(Number));
  assert.ok(west < 39.72 && south < 43.59 && east > 40.27 && north > 43.67);
});

test("map focuses the selected place without pretending district coordinates are exact", () => {
  const points = [
    { id: "hotel", lon: 39.72, lat: 43.59, approximate: false },
    { id: "district", lon: 40.2, lat: 43.68, approximate: true },
  ];
  const exact = new URL(tripMapUrls(points, "hotel").embed);
  assert.equal(exact.searchParams.get("pt"), "39.72,43.59");
  assert.equal(exact.searchParams.get("ll"), "39.72,43.59");
  assert.equal(exact.searchParams.get("z"), "16");
  assert.equal(new URL(tripMapUrls(points, "district").embed).searchParams.get("z"), "12");
  assert.equal(tripMapUrls(points, "deleted").embed, tripMapUrls(points).embed);
  const empty = new URL(tripMapUrls([]).embed);
  assert.equal(empty.searchParams.get("pt"), null);
  assert.equal(empty.searchParams.get("ll"), "95,62");
});

test("map drops invalid coordinates and recovers a later valid copy of a place", () => {
  const state = { options: [{ days: [{ candidates: [
    { id: "a", area: "Сочи", coordinates: { lat: 43.59 } },
    { id: "a", coordinates: { lat: 43.59, lon: 39.72 } },
    { id: "b", coordinates: { lat: Infinity, lon: 39.72 } },
    { id: "c", coordinates: { lat: "43.59", lon: "39.72" } },
  ] }] }] };
  const points = tripMapPoints(state);
  assert.equal(points.length, 1);
  assert.equal(points[0].id, "a");
  assert.equal(points[0].approximate, false);
});

test("reopening a running dialogue does not repeat a persisted pending message", async () => {
  const { pendingText } = await import("./format.js");
  const messages = [{ role: "assistant", text: "Когда поедете?" }, { role: "user", text: "В декабре" }];
  assert.equal(pendingText(messages, "В декабре"), "");
  assert.equal(pendingText(messages, "На неделю"), "На неделю");
  assert.equal(pendingText([...messages, { role: "assistant", text: "Уточните даты" }], "В декабре"), "В декабре");
});
