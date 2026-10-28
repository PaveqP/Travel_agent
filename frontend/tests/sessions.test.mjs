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
  const context = await browser.newContext({ viewport: options.viewport || { width: 1440, height: 900 }, reducedMotion: "reduce" });
  t.after(() => context.close());
  const page = await context.newPage();
  page.setDefaultTimeout(7000);
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error" && !message.text().startsWith("Failed to load resource")) errors.push(message.text()); });
  t.after(() => assert.deepEqual(errors, []));
  const trips = new Map([["existing", snapshot([
    { role: "user", text: "Хочу в горы" }, { role: "assistant", text: "Из какого города поедете?" },
  ])]]);
  if (options.state) trips.set("existing", options.state);
  const chats = new Map();
  let nextId = 0;
  let nextChatId = 0;
  await page.route("**/*", async (route) => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    if (url.origin !== origin) return route.abort();
    const json = (data) => route.fulfill({ json: data });
    if (path === "/api/account") return json({ id: "fixture", name: "Тест", interests: [], city: "", phone: "", telegram_linked: false });
    if (path === "/api/destinations") return json([]);
    if (path === "/api/support") return json([{ id: "flight", title: "Задержка рейса", description: "Помощь с рейсом", steps: ["Проверьте табло"], subject: "Обращение", letter: "Детали обращения" }]);
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
      if (action === "support/flight") return json({ id: "flight", title: "Задержка рейса", steps: ["Проверьте табло"], subject: "Обращение", letter: "Детали обращения" });
      if (action?.startsWith("chats")) {
        const [, chatId, chatAction] = action.split("/");
        if (!chatId && request.method() === "POST") {
          const chat = { chat_id: `chat-${++nextChatId}`, ...request.postDataJSON(), revision: 0, messages: [] };
          chat.title ||= chat.kind === "support" ? "Помощь в пути" : "Вопросы о поездке";
          chats.set(chat.chat_id, chat);
          return json(chat);
        }
        if (!chatId) return json([...chats.values()]);
        const chat = chats.get(chatId);
        if (!chat) return route.fulfill({ status: 404, json: { detail: "Чат не найден" } });
        if (request.method() === "DELETE") { chats.delete(chatId); return route.fulfill({ status: 204 }); }
        if (chatAction === "messages") {
          const { message } = request.postDataJSON();
          options.chatStarted?.resolve(chatId);
          await options.chatGate?.promise;
          chat.messages.push({ role: "user", text: message }, { role: "assistant", text: `Ответ в ${chatId}` });
          chat.revision++;
        }
        return json(chat);
      }
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
      if (action?.startsWith("select/")) {
        const state = trips.get(id);
        state.selected = decodeURIComponent(action.slice(7));
        return json(state);
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
  return { page, trips, chats };
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

function offersState() {
  const price = (amount, basis) => ({ amount, basis, currency: "RUB" });
  const source = { evidence: "live", expires_at: "2099-01-01T00:00:00Z", provider: "tutu" };
  const flight = { id: "flight", role: "transport", name: "Билеты Петербург — Сочи", url: "https://www.tutu.ru/avia/", transport_mode: "avia", start: "2026-11-18", end: "2026-11-22", price: price("17222", "party"), source };
  const hotels = [
    { id: "hotel-a", role: "stays", name: "Солнечный День", area: "Адлер", url: "https://hotel.tutu.ru/hotel-a", start: "2026-11-18", end: "2026-11-22", price: price("24000", "room_stay"), source },
    { id: "hotel-b", role: "stays", name: "Морской парк", area: "Сириус", url: "https://hotel.tutu.ru/hotel-b", start: "2026-11-18", end: "2026-11-22", price: price("28000", "room_stay"), source },
  ];
  const options = hotels.map((stay, index) => ({ id: `option-${index}`, revision: 1, transport: flight, stay, days: [{ date: "2026-11-18", candidates: [{ id: "walk", name: "Прогулка у моря" }] }], budget: { known_subtotal: index ? "45222" : "41222" } }));
  const state = { ...snapshot(), revision: 1, stage: "review", status: "ready", selected: "option-0", constraints: { origin: "Санкт-Петербург", destination: "Сочи", adults: 1, start: "2026-11-18", end: "2026-11-22" }, results: { transport: { candidates: [flight] }, stays: { candidates: hotels } }, options, choices: options.map(({id}) => ({ id })) };
  state.messages = [{ role: "user", text: "Сравни отели" }, { role: "assistant", text: "Сохранил два отеля для сравнения.", presentation: structuredClone(state) }];
  return state;
}

test("right panel preserves chat, links offer names and selects the corresponding package", async (t) => {
  const { page, trips } = await openSession(t, { state: offersState() });
  const panel = page.getByRole("complementary", { name: "Варианты поездки" });
  await panel.waitFor();
  await panel.getByRole("heading", { name: "Туры под ключ", exact: true }).waitFor();
  assert.equal(await panel.locator(".package-card").count(), 2);
  await panel.getByRole("button", { name: "Выбрать вариант 2", exact: true }).click();
  await page.waitForFunction(() => document.querySelector('.saved-artifacts').textContent.includes('Морской парк'));
  assert.equal(trips.get("existing").selected, "option-1");
  await panel.locator(".package-card").first().locator("summary").click();
  await panel.locator(".package-card").first().locator(".day-plan").getByText("Прогулка у моря", { exact: true }).waitFor();
  await page.screenshot({path:"/tmp/flinters-tours-desktop.png"});
  await panel.getByRole("button", { name: "Выбрать вариант 1", exact: true }).click();
  await page.waitForFunction(() => document.querySelector('.saved-artifacts').textContent.includes('Солнечный День'));
  await panel.getByRole("button", { name: "Отели", exact: true }).click();
  assert.equal(await page.locator(".conversation-scroll .package-card").count(), 0);
  assert.equal(await panel.getByRole("link", { name: "Солнечный День" }).getAttribute("href"), "https://hotel.tutu.ru/hotel-a");
  await panel.getByRole("button", { name: /Сравнить · 2/ }).click();
  await panel.getByRole("group", { name: "Сравнение вариантов" }).waitFor();
  await panel.getByRole("button", { name: "Выбрать вариант", exact: true }).click();
  await page.waitForFunction(() => document.querySelector('.saved-artifacts').textContent.includes('Морской парк'));
  assert.equal(trips.get("existing").selected, "option-1");
  await page.locator('.saved-artifacts button').filter({hasText:'Билеты'}).click();
  await panel.getByRole("heading", { name: "Билеты", exact: true }).waitFor();
  assert.equal(await panel.getByRole("link", { name: "Билеты Петербург — Сочи" }).getAttribute("href"), "https://www.tutu.ru/avia/");
  await page.locator('.saved-artifacts button').filter({hasText:'Программа'}).click();
  await panel.getByText("Прогулка у моря", {exact:true}).waitFor();
  await page.locator('.saved-artifacts button').filter({hasText:'Бюджет'}).click();
  await panel.getByRole("heading", { name: "Стоимость поездки" }).waitFor();
  await panel.getByRole("button", { name: "Закрыть панель вариантов" }).click();
  await panel.waitFor({state:'detached'});
  assert.equal(await page.getByRole("textbox", {name:"Сообщение ассистенту"}).isVisible(), true);
});

test("help starts a separate trip chat, preserves plan and keeps chat drafts isolated", async (t) => {
  const { page, trips, chats } = await openSession(t, { state: offersState() });
  const original = structuredClone(trips.get("existing"));
  await page.getByRole("button", {name: /Помощь в пути/}).click();
  assert.equal(await page.getByText(/Справочник помогает подготовить обращение/).count(),0);
  await page.getByRole("button", {name: /Задержка рейса/}).click();
  await page.getByRole("button", {name: "Обсудить с ассистентом", exact:true}).click();
  await page.waitForURL('**/#plan/existing/chat-1');
  const input = page.getByRole('textbox',{name:'Сообщение ассистенту'});
  await page.waitForFunction(()=>document.querySelector('textarea')?.value.includes('Помоги составить письмо'));
  await send(page,'У меня задержка рейса');
  await page.getByText('Ответ в chat-1',{exact:true}).waitFor();
  await page.screenshot({path:'/tmp/flinters-help.png'});
  assert.deepEqual(trips.get('existing'),original);
  assert.equal(chats.get('chat-1').messages.length,2);
  await input.fill('Черновик помощи');
  await page.getByRole('button',{name:'План поездки',exact:true}).click();
  await page.getByText('Сохранил два отеля для сравнения.',{exact:true}).waitFor();
  assert.equal(await input.inputValue(),'');
  await input.fill('Черновик плана');
  await page.getByRole('button',{name:'Помоги составить письмо: Задержка рейса',exact:true}).click();
  await page.getByText('Ответ в chat-1',{exact:true}).waitFor();
  assert.equal(await input.inputValue(),'Черновик помощи');
  await page.reload();
  await page.getByText('Ответ в chat-1',{exact:true}).waitFor();
  assert.equal(await page.getByText('У меня задержка рейса',{exact:true}).count(),1);
});

test("a background help answer cannot appear in the plan chat", async (t) => {
  const chatGate=deferred(),chatStarted=deferred();
  t.after(()=>chatGate.resolve());
  const {page}=await openSession(t,{state:offersState(),chatGate,chatStarted});
  await page.getByRole('button',{name:'Новый чат поездки'}).click();
  await page.getByRole('button',{name:'Создать чат',exact:true}).click();
  await page.waitForURL('**/#plan/existing/chat-1');
  await send(page,'Вопрос в отдельном чате');
  await chatStarted.promise;
  await page.getByRole('button',{name:'План поездки',exact:true}).click();
  const response=page.waitForResponse(r=>r.url().endsWith('/chats/chat-1/messages'));
  chatGate.resolve();await response;
  await page.getByText('Сохранил два отеля для сравнения.',{exact:true}).waitFor();
  assert.equal(await page.getByText('Ответ в chat-1',{exact:true}).count(),0);
});

test("on a phone the options panel is an accessible sheet and does not overflow", async (t) => {
  const {page}=await openSession(t,{state:offersState(),viewport:{width:390,height:844}});
  assert.equal(await page.getByRole('dialog').count(),0);
  await page.getByRole('button',{name:'Открыть меню',exact:true}).click();
  await page.locator('.saved-artifacts button').filter({hasText:'Проживание'}).click();
  const sheet=page.getByRole('dialog');await sheet.waitFor();
  await sheet.getByRole('heading',{name:'Отели',exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
  await page.screenshot({path:'/tmp/flinters-options-mobile.png'});
  await sheet.getByRole('button',{name:'Закрыть',exact:true}).click();
  await sheet.waitFor({state:'detached'});
  assert.equal(await page.getByRole('textbox',{name:'Сообщение ассистенту'}).isVisible(),true);
});

test("main service pages, unknown routes and trip chat deletion stay consistent", async(t)=>{
  const {page,chats}=await openSession(t,{state:offersState()});
  for(const [route,heading] of [['trip/existing','Ваша поездка, целиком'],['track/existing','Хорошо, когда всё под рукой.'],['support/existing','Мы рядом. Разберёмся.'],['profile','Личный кабинет'],['trips','Мои поездки']]){
    await page.goto(origin+'/#'+route);
    await page.getByRole('heading',{name:heading,exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
  }
  await page.goto(origin+'/#unknown');
  await page.getByRole('heading',{name:'Страница не найдена'}).waitFor();
  await page.goto(origin+'/#plan/existing');
  await page.getByRole('button',{name:'Новый чат поездки'}).click();
  await page.getByRole('button',{name:'Создать чат',exact:true}).click();
  await page.waitForURL('**/#plan/existing/chat-1');
  await page.getByRole('button',{name:'Удалить чат: Вопросы о поездке',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Удалить чат',exact:true}).click();
  await page.waitForURL('**/#plan/existing');
  assert.equal(chats.size,0);
  await page.getByText('Сохранил два отеля для сравнения.',{exact:true}).waitFor();
});

test("the legacy day approval remains available in the itinerary panel", async(t)=>{
  const state=offersState();state.autonomous=false;state.stage='itinerary';
  state.choices=[{id:'option-0',title:'Согласовать программу'}];
  const {page}=await openSession(t,{state});
  const panel=page.getByRole('complementary',{name:'Варианты поездки'});
  await panel.getByRole('heading',{name:'Программа по дням',exact:true}).waitFor();
  assert.equal(await panel.getByRole('button',{name:'Мне подходит, собери поездку'}).isEnabled(),true);
});

test("tour sheet works on phones and Markdown stays safe and readable", async (t) => {
  const state = offersState();
  state.messages.at(-1).text = "**Сургут**\n\n- Перелёт и отель\n- Программа по дням\n\n[Отель](https://example.com)\n<script>window.injected=true</script>";
  const { page } = await openSession(t, { state, viewport: { width: 390, height: 844 } });
  await page.locator(".chat-markdown strong").filter({ hasText: "Сургут" }).waitFor();
  assert.equal(await page.locator(".chat-markdown li").count(), 2);
  assert.equal(await page.locator(".chat-markdown script").count(), 0);
  assert.equal(await page.evaluate(() => window.injected), undefined);
  await page.getByRole("button", { name: "Открыть варианты поездки", exact: true }).click();
  const sheet = page.getByRole("dialog");
  await sheet.getByRole("heading", { name: "Туры под ключ", exact: true }).waitFor();
  assert.equal(await sheet.locator(".package-card").count(), 2);
  await sheet.getByRole("button", { name: "Выбрать вариант 2", exact: true }).click();
  await sheet.locator(".package-card").last().getByText("Выбран", { exact: true }).waitFor();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  await page.screenshot({ path: "/tmp/flinters-tours-mobile.png" });
});
