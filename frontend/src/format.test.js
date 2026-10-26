import { test } from "node:test";
import assert from "node:assert/strict";
import { money, safeUrl, tripStatus, currentOption } from "./format.js";

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
