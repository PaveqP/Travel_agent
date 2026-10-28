import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { chromium } from "playwright";
import { createServer } from "vite";

let server, browser, origin;
before(async () => {
  server = await createServer({ server: { host: "127.0.0.1", port: 0 } });
  await server.listen();
  origin = `http://127.0.0.1:${server.httpServer.address().port}`;
  browser = await chromium.launch({ headless: true });
});
after(async () => {
  await browser?.close();
  await server?.close();
});

const deferred = () => {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
};
const snapshot = (messages = []) => ({
  autonomous: true, stage: "scenarios", revision: 0, status: "needs_input",
  constraints: {}, messages, results: {}, options: [], cards: [], choices: [],
});

async function openSession(t, options = {}) {
  const context = await browser.newContext();
  t.after(() => context.close());
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  t.after(() => assert.deepEqual(errors, []));
  const trips = new Map([["existing", snapshot([
    { role: "user", text: "Хочу в горы" }, { role: "assistant", text: "Из какого города поедете?" },
  ])]]);
  let nextId = 0;
  await page.route("**/*", async (route) => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    if (url.origin !== origin) return route.abort();
    const json = (data) => route.fulfill({ json: data });
    if (path === "/api/account") return json({ id: "fixture", name: "Тест" });
    if (path === "/api/support") return json([]);
    if (path === "/trips" && request.method() === "POST") {
      const id = `new-${++nextId}`;
      trips.set(id, snapshot());
      return json({ trip_id: id, revision: 0 });
    }
    if (path === "/trips") {
      await options.historyGate?.promise;
      return json([...trips].map(([trip_id, state]) => ({ trip_id, state })));
    }
    const match = path.match(/^\/trips\/([^/]+)(?:\/(.*))?$/);
    if (match) {
      const [, id, action] = match;
      if (action === "events") return route.fulfill({ contentType: "text/event-stream", body: 'data: {"status":"running","label":"Подбор","previews":{}}\n\n' });
      if (action === "messages") {
        if (options.failMessages) return route.fulfill({ status: 504, json: { detail: "Turn deadline exceeded; read current trip state before retrying" } });
        const { message } = request.postDataJSON();
        trips.get(id).messages.push({ role: "user", text: message });
        options.started?.resolve(id);
        if (id === "existing") await options.messageGate?.promise;
        trips.get(id).messages.push({ role: "assistant", text: `Ответ для ${id}` });
        return json(trips.get(id));
      }
      if (!action) {
        const state = structuredClone(trips.get(id));
        if (options.delayRead?.(id)) {
          options.readStarted?.resolve();
          await options.readGate.promise;
        }
        return json(state);
      }
      return json({});
    }
    if (path.startsWith("/api/")) return json({});
    return route.continue();
  });
  await page.goto(origin + (options.empty ? "/#plan" : "/#plan/existing"));
  await page.getByRole("textbox", { name: "Сообщение ассистенту" }).waitFor();
  return { page, trips };
}

async function send(page, text) {
  await page.getByRole("textbox", { name: "Сообщение ассистенту" }).fill(text);
  await page.getByRole("button", { name: "Отправить сообщение" }).click();
}

test("empty dialogue has no map or duplicate sidebar history", async (t) => {
  const { page } = await openSession(t, { empty: true });
  await page.getByRole("heading", { name: /Ваш отпуск начинается/ }).waitFor();
  assert.equal(await page.locator("iframe").count(), 0);
  assert.equal(await page.getByText("МОИ ПЛАНЫ", { exact: false }).count(), 0);
  assert.equal(await page.getByRole("button", { name: /Мои поездки/ }).count(), 1);
});

test("new trip can start while another session is still processing", async (t) => {
  const messageGate = deferred(), started = deferred();
  t.after(() => messageGate.resolve());
  const { page, trips } = await openSession(t, { messageGate, started });
  await send(page, "Подбери на неделю");
  await started.promise;
  await page.getByRole("button", { name: "Новая поездка" }).click();
  await page.getByRole("heading", { name: /Ваш отпуск начинается/ }).waitFor();
  await send(page, "Другая поездка");
  await page.getByText("Ответ для new-1", { exact: true }).waitFor();
  const oldFinished = page.waitForResponse((response) => response.url().endsWith('/trips/existing/messages'));
  messageGate.resolve();
  await oldFinished;
  await page.waitForFunction(() => !document.querySelector(".agent-thinking"));
  assert.equal(await page.getByText("Ответ для existing", { exact: true }).count(), 0);
  assert.equal(trips.size, 2);
  assert.equal(trips.get("new-1").messages[0].text, "Другая поездка");
});

test("reopening a running session and reloading preserves each message once", async (t) => {
  const messageGate = deferred(), started = deferred();
  t.after(() => messageGate.resolve());
  const { page } = await openSession(t, { messageGate, started });
  await send(page, "В декабре вдвоём");
  await started.promise;
  await page.getByRole("button", { name: /Мои поездки/ }).click();
  const fetched = page.waitForResponse((response) => response.url().endsWith('/trips/existing'));
  await page.locator(".history-open-button").click();
  await fetched;
  await page.getByText("В декабре вдвоём", { exact: true }).first().waitFor();
  assert.equal(await page.getByText("В декабре вдвоём", { exact: true }).count(), 1);
  messageGate.resolve();
  await page.getByText("Ответ для existing", { exact: true }).waitFor();
  await page.reload();
  await page.getByText("Ответ для existing", { exact: true }).waitFor();
  assert.equal(await page.getByText("Ответ для existing", { exact: true }).count(), 1);
  assert.equal(await page.getByText("В декабре вдвоём", { exact: true }).count(), 1);
});

test("a delayed load cannot overwrite a newer completed answer", async (t) => {
  const readGate = deferred(), readStarted = deferred(), messageGate = deferred(), started = deferred();
  let reads = 0;
  t.after(() => { readGate.resolve(); messageGate.resolve(); });
  const { page } = await openSession(t, { readGate, readStarted, messageGate, started,
    delayRead: (id) => id === "existing" && ++reads === 2 });
  await send(page, "Новый запрос");
  await started.promise;
  await page.getByRole("button", { name: /Мои поездки/ }).click();
  await page.locator(".history-open-button").click();
  await readStarted.promise;
  messageGate.resolve();
  await page.getByText("Ответ для existing", { exact: true }).waitFor();
  const loaded = page.waitForResponse((response) => response.url().endsWith('/trips/existing'));
  readGate.resolve();
  await loaded;
  await page.getByRole("textbox", { name: "Сообщение ассистенту" }).waitFor({ state: "visible" });
  assert.equal(await page.getByText("Ответ для existing", { exact: true }).count(), 1);
});

test("a failed first message shows the error and restores its draft in the created trip", async (t) => {
  const { page } = await openSession(t, { empty: true, failMessages: true });
  await send(page, "Сохрани мой запрос");
  await page.getByText(/Подбор занял больше времени/).waitFor();
  await page.waitForFunction(() => document.querySelector("textarea")?.value === "Сохрани мой запрос");
  assert.equal(await page.getByRole("textbox", { name: "Сообщение ассистенту" }).isEnabled(), true);
});
