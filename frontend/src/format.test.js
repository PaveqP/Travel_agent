import { test } from "node:test";
import assert from "node:assert/strict";
import {
  money,
  safeUrl,
  tripStatus,
  currentOption,
  tripParts,
  tripMapPoints,
} from "./format.js";

test("unknown costs are distinct from zero", () => {
  assert.equal(money(null), "Уточняется");
  assert.match(money(0), /0/);
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
  assert.equal(party(1, []), "1 взрослых");
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
  assert.equal(points.length, 3);
  assert.equal(points[0].kind, "transport");
  assert.equal(points[1].approximate, true);
  assert.equal(points[1].area, "Сириус");
  assert.equal(points[2].approximate, false);
  assert.ok(Math.abs(points[2].x - 400) < 0.001);
  assert.deepEqual(tripMapPoints(null), []);
});
