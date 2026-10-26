import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowUp,
  ArrowUpRight,
  ArrowRight,
  ArrowLeft,
  Check,
  ChevronRight,
  ChevronDown,
  X,
  Plus,
  Plane,
  Building2,
  MapPin,
  Mountain,
  Waves,
  Sparkles,
  CalendarDays,
  Users,
  Send,
  MessageCircle,
  Compass,
  Clock3,
  History,
  CircleUserRound,
  LogOut,
  Download,
  CreditCard,
  ShieldCheck,
  LifeBuoy,
  Copy,
  CheckCircle2,
  Menu,
  LoaderCircle,
  Luggage,
  Mail,
  ExternalLink,
  SlidersHorizontal,
  Route,
  Sun,
  Wallet,
  Trash2,
  Link2,
  LockKeyhole,
} from "lucide-react";
import {
  stages,
  stageNames,
  money,
  date,
  time,
  basis,
  safeUrl,
  currentOption,
  tripStatus,
} from "./format";
import "./styles.css";

const TELEGRAM = "https://t.me/ostrovok_helper_ryadom_bot";
const inspiration = [
  {
    title: "В ритме моря",
    place: "Сочи · Адлер · Сириус",
    image: "sea",
    icon: Waves,
    text: "Хочу в Сочи к морю: неспешные прогулки, вкусная еда и отель рядом с набережной",
  },
  {
    title: "Выше только облака",
    place: "Красная Поляна · Роза Хутор",
    image: "mountains",
    icon: Mountain,
    text: "Хочу в Красную Поляну: горы, красивые виды и уютный отель. Помоги спланировать поездку",
  },
  {
    title: "Всё и чуть больше",
    place: "Большой Сочи",
    image: "cable",
    icon: Compass,
    text: "Хочу совместить море, горы и интересные места в Большом Сочи. Предложи варианты поездки",
  },
];

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
    body: options.body == null ? undefined : JSON.stringify(options.body),
  });
  if (!response.ok) {
    let detail;
    try {
      detail = (await response.json()).detail;
    } catch {
      detail = null;
    }
    const translated = {
      "Stale revision": "План изменился. Обновили его — повторите выбор.",
      "Quotes expired; refresh search":
        "Цены устарели. Попросите ассистента обновить предложения.",
      "Trip not found": "Эта поездка недоступна.",
      "Invalid bearer token": "Войдите в личный кабинет.",
      "Turn deadline exceeded; read current trip state before retrying":
        "Подбор занял больше времени. Обновите поездку перед повтором.",
    };
    const error = new Error(
      typeof detail === "string"
        ? translated[detail] || detail
        : response.status === 422
          ? "Проверьте поля формы: некоторые значения не подходят."
          : "Не удалось выполнить действие. Попробуйте ещё раз.",
    );
    error.status = response.status;
    throw error;
  }
  return response.status === 204 ? null : response.json();
}

function Icon({ of: Component, ...props }) {
  return <Component size={20} strokeWidth={1.7} {...props} />;
}
function TelegramLink({ className = "", children = "В Telegram" }) {
  return (
    <a className={className} href={TELEGRAM} target="_blank" rel="noreferrer">
      <Icon of={Send} />
      {children}
      <ArrowUpRight size={15} />
    </a>
  );
}
function Brand() {
  return (
    <a className="brand" href="#plan" aria-label="О! рядом — главная">
      <span className="brand-mark">О!</span>
      <span>
        рядом<span className="brand-sub">путешествуем вместе</span>
      </span>
    </a>
  );
}

function Modal({ title, children, close, wide = false }) {
  const ref = useRef(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog.showModal();
    const stop = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        close();
      }
    };
    dialog.addEventListener("keydown", stop);
    return () => dialog.removeEventListener("keydown", stop);
  }, []);
  return (
    <dialog
      ref={ref}
      className={`modal ${wide ? "modal-wide" : ""}`}
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div className="modal-head">
        <h2>{title}</h2>
        <button className="icon-button" onClick={close} aria-label="Закрыть">
          <X />
        </button>
      </div>
      {children}
    </dialog>
  );
}

function Auth({ close, authenticated, run }) {
  const [register, setRegister] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault();
    setError("");
    setPending(true);
    const data = Object.fromEntries(new FormData(e.currentTarget));
    try {
      const account = await api(
        "/api/auth/" + (register ? "register" : "login"),
        { method: "POST", body: data },
      );
      authenticated(account);
      close();
    } catch (e) {
      setError(e.message);
    } finally {
      setPending(false);
    }
  }
  return (
    <Modal
      title={register ? "Место для ваших путешествий" : "С возвращением!"}
      close={close}
    >
      <p className="muted">Сохраним планы и будем рядом на каждом шаге.</p>
      <div className="segmented">
        <button
          className={register ? "active" : ""}
          onClick={() => {
            setRegister(true);
            setError("");
          }}
        >
          Создать аккаунт
        </button>
        <button
          className={!register ? "active" : ""}
          onClick={() => {
            setRegister(false);
            setError("");
          }}
        >
          Войти
        </button>
      </div>
      <form className="form" onSubmit={submit}>
        {register && (
          <label>
            Как вас зовут
            <input
              name="name"
              required
              maxLength={80}
              autoComplete="given-name"
              placeholder="Ваше имя"
            />
          </label>
        )}
        <label>
          Email
          <input
            type="email"
            name="email"
            required
            autoComplete="email"
            maxLength={254}
            placeholder="you@example.ru"
          />
        </label>
        <label>
          Пароль
          <input
            type="password"
            name="password"
            required
            minLength={register ? 10 : 1}
            maxLength={128}
            autoComplete={register ? "new-password" : "current-password"}
            placeholder={register ? "Не менее 10 символов" : "Ваш пароль"}
          />
        </label>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <button className="primary" disabled={pending}>
          {pending ? (
            <LoaderCircle className="spin" size={18} />
          ) : (
            <ArrowRight size={18} />
          )}
          {register ? "Создать аккаунт" : "Войти"}
        </button>
      </form>
      <a
        className="telegram-auth secondary"
        href={TELEGRAM + "?start=web_login"}
        target="_blank"
        rel="noreferrer"
      >
        <Send size={16} />
        Войти через Telegram
      </a>
      <p className="small muted">
        <LockKeyhole size={13} /> Личные планы доступны только вам.
      </p>
    </Modal>
  );
}

function Composer({ value, setValue, send, busy, compact = false }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current) {
      ref.current.style.height = "auto";
      ref.current.style.height = Math.min(ref.current.scrollHeight, 155) + "px";
    }
  }, [value]);
  return (
    <form
      className={`composer ${compact ? "compact" : ""}`}
      onSubmit={(e) => {
        e.preventDefault();
        send();
      }}
    >
      <textarea
        ref={ref}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        maxLength={4000}
        rows={compact ? 2 : 3}
        aria-label="Сообщение ассистенту"
        placeholder={
          compact
            ? "Спросите или измените пожелания…"
            : "Хочу к морю на неделю. Вдвоём, из Москвы, без суеты…"
        }
        disabled={busy}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            if (!busy) send();
          }
        }}
      />
      <div className="composer-bottom">
        <span>
          <Sparkles size={14} />
          {busy
            ? "Собираем ваши варианты…"
            : compact
              ? "Можно просто своими словами"
              : "Вы мечтаете. Мы собираем поездку."}
        </span>
        <button
          className="send-button"
          type="submit"
          disabled={busy || !value.trim()}
          aria-label="Отправить сообщение"
        >
          {busy ? (
            <LoaderCircle className="spin" size={21} />
          ) : (
            <ArrowUp size={22} />
          )}
        </button>
      </div>
    </form>
  );
}

function Home({ value, setValue, send, busy, user }) {
  return (
    <>
      <section className="hero">
        <div className="hero-copy">
          <div className="eyebrow">
            <span className="live-dot" /> ВАШ ЛИЧНЫЙ ПОМОЩНИК В ПУТЕШЕСТВИЯХ
          </div>
          <h1>
            Весь отпуск.
            <br />
            <span>В одном разговоре.</span>
            <span className="hand-star">✳</span>
          </h1>
          <p className="hero-description">
            Просто расскажите, куда зовёт настроение.
            <br />
            Билеты, отель и впечатления — соберём всё вместе.
          </p>
          <Composer value={value} setValue={setValue} send={send} busy={busy} />
          <div className="hero-hints">
            <span>Начнём с идеи?</span>
            <button
              onClick={() =>
                setValue(
                  "Хочу в Большой Сочи, пока не определился с датами. Предложи идеи для поездки",
                )
              }
            >
              <Sun size={14} /> Хочу к морю
            </button>
            <button onClick={() => setValue(inspiration[1].text)}>
              <Mountain size={14} /> Тянет в горы
            </button>
          </div>
        </div>
        <div
          className="hero-visual"
          aria-label="Вдохновение для поездки в Большой Сочи"
        >
          <div className="photo-main">
            <img src="/images/sea.jpg" alt="Морское побережье Сочи" />
            <div className="photo-shade" />
            <span className="photo-label">
              <MapPin size={15} /> Большой Сочи
            </span>
            <div className="photo-caption">
              Ближе к морю.
              <br />
              Ближе к себе.
            </div>
            <div className="photo-number">01 / 03</div>
          </div>
          <div className="photo-secondary">
            <img src="/images/mountains.jpg" alt="Горы Розы Хутор" />
            <span>
              <Mountain size={15} /> А может, в горы?
            </span>
          </div>
          <div className="glass-ticket">
            <span className="glass-icon">
              <Sparkles size={22} />
            </span>
            <div>
              <strong>Хороший план — уже отдых</strong>
              <span>Всё важное в одном месте</span>
            </div>
            <span className="glass-check">
              <Check size={16} />
            </span>
          </div>
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <span className="sun-sticker">✺</span>
        </div>
      </section>
      <section className="inspiration">
        <div className="section-heading">
          <div>
            <div className="eyebrow">СТОЛЬКО ВСЕГО РЯДОМ</div>
            <h2>Какой отдых — ваш?</h2>
          </div>
          <span className="muted">Одна поездка. Много возможностей.</span>
        </div>
        <div className="inspiration-grid">
          {inspiration.map((item) => (
            <button
              className="inspire-card"
              key={item.title}
              onClick={() => {
                setValue(item.text);
                window.scrollTo({ top: 0, behavior: "smooth" });
              }}
            >
              <img src={`/images/${item.image}.jpg`} alt="" />
              <div className="inspire-shade" />
              <span className="inspire-icon">
                <Icon of={item.icon} />
              </span>
              <div>
                <h3>{item.title}</h3>
                <p>{item.place}</p>
              </div>
              <span className="inspire-arrow">
                <ArrowUpRight size={21} />
              </span>
            </button>
          ))}
        </div>
      </section>
      <div className="value-strip">
        <div>
          <ShieldCheck />
          <span>
            <strong>Вы решаете на каждом шаге</strong>Любой выбор можно обсудить
            и изменить
          </span>
        </div>
        <div>
          <Route />
          <span>
            <strong>От первой идеи до возвращения</strong>Маршрут, документы и
            помощь под рукой
          </span>
        </div>
        <div>
          <Send />
          <span>
            <strong>Удобнее в Telegram?</strong>
            <a href={TELEGRAM} target="_blank" rel="noreferrer">
              Продолжим там <ArrowUpRight size={13} />
            </a>
          </span>
        </div>
      </div>
      <div className="demo-note">
        MVP сервиса · Планируем Большой Сочи · Оплата и бронирование имитируются
      </div>
    </>
  );
}

function Chat({ state, value, setValue, send, busy, newTrip }) {
  const bottom = useRef(null);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [state?.messages?.length, busy]);
  return (
    <aside className="chat-panel">
      <div className="chat-heading">
        <span className="assistant-avatar">
          <Sparkles size={21} />
        </span>
        <div>
          <strong>Ваш О! помощник</strong>
          <span>
            <i /> Рядом на каждом шаге
          </span>
        </div>
        <button
          onClick={newTrip}
          className="icon-button"
          title="Новая поездка"
          aria-label="Новая поездка"
        >
          <Plus size={19} />
        </button>
      </div>
      <div className="chat-messages">
        <div className="chat-day">Планируем хорошее</div>
        <div className="message assistant">
          <span className="message-label">О! рядом</span>
          <p>
            Привет! Расскажите о поездке мечты — я помогу превратить её в
            понятный план. Всё можно обсудить и поменять.
          </p>
        </div>
        {state?.messages?.map((m, i) => (
          <div className={`message ${m.role}`} key={i}>
            {m.role === "assistant" && (
              <span className="message-label">О! рядом</span>
            )}
            <p>
              {m.role === "user" && m.text.startsWith("/select ")
                ? "Выбираю этот вариант"
                : m.text}
            </p>
          </div>
        ))}
        {busy && (
          <div className="message assistant thinking">
            <span />
            <span />
            <span />
            <small>Подбираю варианты</small>
          </div>
        )}
        <div ref={bottom} />
      </div>
      <div className="chat-compose">
        <Composer
          compact
          value={value}
          setValue={setValue}
          send={send}
          busy={busy}
        />
        <span className="chat-disclaimer">
          Ассистент может ошибаться. Проверяйте важные детали.
        </span>
      </div>
    </aside>
  );
}

function SourceLink({ url, children }) {
  const href = safeUrl(url);
  return href ? (
    <a className="source-link" href={href} target="_blank" rel="noreferrer">
      {children || "Посмотреть источник"}
      <ExternalLink size={12} />
    </a>
  ) : null;
}

function ChoiceCard({ choice, state, index, choose, busy }) {
  const stage = state.stage;
  const scenario = state.scenarios?.find((s) => s.id === choice.id);
  const candidate = Object.values(state.results || {})
    .flatMap((r) => r.candidates || [])
    .find((c) => c.id === choice.id);
  const card = state.cards?.find((c) => c.id === choice.id);
  const price = choice.price || card?.price || candidate?.price;
  const dates = card?.dates || candidate || {};
  const warnings = [
    ...new Set([
      ...(card?.warnings || []),
      ...(candidate?.source?.evidence && candidate.source.evidence !== "live"
        ? ["Наличие не подтверждено"]
        : []),
    ]),
  ];
  const warningLabels = {
    alternate_dates: "Другие даты",
    unknown_price: "Цена уточняется",
    unverified_availability: "Наличие не подтверждено",
    expired_quote: "Цена устарела",
    different_party: "Другой состав гостей",
    outside_search_window: "Вне ваших дат",
    direct_flight_unverified: "Прямой рейс не подтверждён",
    over_budget: "Выше бюджета",
    different_area: "Другой район",
  };
  return (
    <article
      className={`choice-card ${stage === "transport" ? "ticket-card" : ""}`}
      style={{ "--delay": `${index * 75}ms` }}
    >
      {stage === "scenarios" ? (
        <>
          <div className="scenario-image">
            <img
              src={`/images/${/Полян|Хутор/.test(scenario?.destination) ? "mountains" : index % 2 ? "cable" : "sea"}.jpg`}
              alt={scenario?.destination || "Большой Сочи"}
            />
            <span className="image-pill">
              <MapPin size={12} />
              {scenario?.destination || "Большой Сочи"}
            </span>
            {index === 0 && (
              <span className="recommend-tag">
                <Sparkles size={12} /> С этого начнём?
              </span>
            )}
          </div>
          <div className="choice-content">
            <span className="choice-kicker">
              ВАРИАНТ {String(index + 1).padStart(2, "0")}
            </span>
            <h3>{choice.title}</h3>
            <p>{scenario?.purpose || choice.details}</p>
            {scenario?.interests?.length > 0 && (
              <div className="tags">
                {scenario.interests.map((t) => (
                  <span key={t}>{t}</span>
                ))}
              </div>
            )}
            <p className="tradeoff">{scenario?.tradeoff}</p>
            <button
              className="primary choice-button"
              disabled={busy}
              onClick={() => choose(choice.id)}
            >
              Хочу так
              <ArrowRight size={16} />
            </button>
            <span className="small muted">
              Цены проверим на следующих шагах
            </span>
          </div>
        </>
      ) : (
        <div className="choice-content">
          <div className="choice-top">
            <span className="provider-icon">
              <Icon of={stage === "transport" ? Plane : Building2} />
            </span>
            <div>
              <span className="choice-kicker">
                {stage === "transport"
                  ? "ТУДА И ОБРАТНО"
                  : candidate?.area || "ПРОЖИВАНИЕ"}
              </span>
              <h3>{choice.title}</h3>
            </div>
            {index === 0 && <span className="soft-badge">Вариант 1</span>}
          </div>
          {stage === "transport" && (
            <div className="flight-route">
              <div>
                <strong>{time(dates.departure_at)}</strong>
                <span>
                  {candidate?.origin ||
                    state.constraints?.origin ||
                    "Отправление"}
                </span>
                <small>{date(dates.start)}</small>
              </div>
              <div className="flight-line">
                <span>
                  {candidate?.duration_minutes
                    ? `${Math.floor(candidate.duration_minutes / 60)} ч ${candidate.duration_minutes % 60} мин`
                    : "Время уточняется"}
                </span>
                <i />
                <small>
                  {candidate?.transfers === 0
                    ? "Прямой"
                    : candidate?.transfers == null
                      ? "Пересадки уточняются"
                      : `${candidate.transfers} пересадок`}
                </small>
              </div>
              <div>
                <strong>{time(dates.arrival_at)}</strong>
                <span>Сочи · AER</span>
                <small>{date(dates.arrival_at || dates.start)}</small>
              </div>
            </div>
          )}
          {stage === "stays" && (
            <div className="stay-dates">
              <CalendarDays size={17} />
              {date(dates.start)} — {date(dates.end)}
              <span>
                <Users size={16} />
                {candidate?.adults || state.constraints?.adults} взрослых
              </span>
            </div>
          )}
          <p>{candidate?.description || card?.description || choice.details}</p>
          {stage === "transport" && dates.return_departure_at && (
            <p className="small">
              Обратно: {date(dates.return_departure_at)} ·{" "}
              {time(dates.return_departure_at)}
            </p>
          )}
          <div className="tags">
            {warnings.map((w) => (
              <span className="warning-tag" key={w}>
                {warningLabels[w] || w}
              </span>
            ))}
          </div>
          <div className="choice-footer">
            <div>
              <strong className="price">{money(price?.amount)}</strong>
              <span className="small muted">
                {basis(price?.basis)} · {price?.currency || "RUB"}
              </span>
            </div>
            <button
              className="primary"
              disabled={busy || card?.freshness === "expired"}
              onClick={() => choose(choice.id)}
            >
              Выбрать
              <ArrowRight size={16} />
            </button>
          </div>
          <div className="source-row">
            <span>
              {card?.aggregator ||
                candidate?.source?.provider ||
                "Поисковое предложение"}
            </span>
            <SourceLink
              url={card?.url || candidate?.url || candidate?.source?.source_url}
            />
          </div>
        </div>
      )}
    </article>
  );
}

function DayPlan({ days = [], completed, toggle }) {
  return (
    <div className="day-plan">
      {days.map((day, i) => (
        <div className="day-item" key={day.date}>
          <div className="day-marker">
            <span>{String(i + 1).padStart(2, "0")}</span>
            <i />
          </div>
          <div className="day-content">
            <div className="day-heading">
              <h3>
                {i === 0
                  ? "Здравствуй, отдых"
                  : i === days.length - 1
                    ? "До новых встреч"
                    : `День ${i + 1}`}
              </h3>
              <span>{date(day.date)}</span>
            </div>
            {day.candidates?.length ? (
              day.candidates.map((c, index) => (
                <div className="activity" key={c.id}>
                  {toggle && (
                    <input
                      aria-label={`Отметить: ${c.name}`}
                      type="checkbox"
                      checked={!!completed?.[`${day.date}:${index}`]}
                      onChange={() => toggle(`${day.date}:${index}`)}
                    />
                  )}
                  <MapPin size={17} />
                  <div>
                    <strong>{c.name}</strong>
                    {c.description && <p>{c.description}</p>}
                    <SourceLink url={c.url || c.source?.source_url} />
                  </div>
                </div>
              ))
            ) : (
              <div className="activity free-time">
                <Sun size={18} />
                <span>
                  Свободное время и переезды
                  <br />
                  <small>Оставим место для спонтанности</small>
                </span>
              </div>
            )}
            {day.warnings?.map((w) => (
              <p className="day-warning" key={w}>
                {w}
              </p>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function Summary({ state, tripId, pay, navigate, download, expanded = false }) {
  const option = currentOption(state);
  const receipt = state.stage === "booked" ? state.receipt : null;
  const c = state.constraints || {};
  const items =
    receipt?.items ||
    [option?.transport, option?.stay]
      .filter(Boolean)
      .map((i) => ({ ...i, kind: i.role }));
  const days = receipt?.itinerary || option?.days || [];
  const total = receipt?.payment?.amount ?? option?.budget?.known_subtotal;
  const componentCost = (item) =>
    item?.price?.amount == null ||
    !["party", "room_stay", "person", "ticket"].includes(item.price.basis)
      ? 0
      : Number(item.price.amount) *
        (["person", "ticket"].includes(item.price.basis) ? c.adults || 1 : 1);
  const transportCost = componentCost(
    items.find((i) => i.kind === "transport"),
  );
  const stayCost = componentCost(items.find((i) => i.kind === "stays"));
  const costSum = transportCost + stayCost;
  return (
    <div className="trip-summary">
      <div className={`summary-banner ${receipt ? "booked" : ""}`}>
        <span>
          <Icon of={receipt ? CheckCircle2 : Luggage} size={26} />
        </span>
        <div>
          <span className="eyebrow">
            {receipt ? "МОЖНО ПРЕДВКУШАТЬ" : "ПАЗЛ СЛОЖИЛСЯ"}
          </span>
          <h2>{receipt ? "Ваш Сочи ждёт" : "Ваша поездка, целиком"}</h2>
          <p>
            {date(c.start)} — {date(c.end)} · {c.adults || "—"} взрослых ·{" "}
            {c.origin || "Город уточняется"}
          </p>
        </div>
      </div>
      {receipt && (
        <div className="notice">
          <ShieldCheck size={19} />
          <span>
            Имитационный заказ № {receipt.id?.slice(0, 8)}. Деньги не списаны,
            места не зарезервированы.
          </span>
        </div>
      )}
      <div className="summary-items">
        {items.map((item, i) => (
          <details className="summary-component" key={i}>
            <summary>
              <span className="component-icon">
                <Icon of={item.kind === "transport" ? Plane : Building2} />
              </span>
              <div>
                <small>
                  {item.kind === "transport"
                    ? "Билеты туда и обратно"
                    : "Ваш отель"}
                </small>
                <strong>{item.name}</strong>
              </div>
              <ChevronDown size={18} />
            </summary>
            <div className="component-details">
              <p>
                {item.description ||
                  item.details?.description ||
                  "Подробности уточняйте у поставщика."}
              </p>
              <p>
                {money(item.price?.amount)} · {basis(item.price?.basis)}
              </p>
              {(item.arrival_at || item.details?.arrival_at) && (
                <p>
                  Прилёт: {date(item.arrival_at || item.details.arrival_at)} ·{" "}
                  {time(item.arrival_at || item.details.arrival_at)}
                </p>
              )}
              {(item.return_departure_at ||
                item.details?.return_departure_at) && (
                <p>
                  Обратно:{" "}
                  {date(
                    item.return_departure_at ||
                      item.details.return_departure_at,
                  )}{" "}
                  ·{" "}
                  {time(
                    item.return_departure_at ||
                      item.details.return_departure_at,
                  )}
                </p>
              )}
              <SourceLink url={item.url || item.source?.source_url} />
            </div>
          </details>
        ))}
      </div>
      <div className="budget-panel">
        <div>
          <span>Билеты + проживание</span>
          <strong>{money(total)}</strong>
        </div>
        <p>
          Известная сумма за всех. Питание, активности, трансферы и
          дополнительные сборы оплачиваются отдельно; их стоимость уточняется.
        </p>
        <div
          className="budget-bar"
          aria-label="Соотношение стоимости билетов и проживания"
        >
          <span
            style={{ flex: transportCost / (costSum || 1) }}
            title={`Билеты: ${money(transportCost)}`}
          />
          <span
            style={{ flex: stayCost / (costSum || 1) }}
            title={`Проживание: ${money(stayCost)}`}
          />
        </div>
        <div className="budget-legend">
          <span>
            <i /> Билеты
          </span>
          <span>
            <i /> Проживание
          </span>
          <span>Без реального списания</span>
        </div>
      </div>
      <div className="summary-actions">
        <button className="secondary" onClick={download}>
          <Download size={17} />
          Маршрут в PDF
        </button>
        {receipt ? (
          <button className="primary" onClick={() => navigate("track", tripId)}>
            <Compass size={17} />В поездку
          </button>
        ) : (
          state.stage === "review" && (
            <button className="primary" onClick={pay}>
              <CreditCard size={17} />К оплате
            </button>
          )
        )}
      </div>
      {expanded && (
        <>
          <h2 className="subheading">Ваша программа</h2>
          <DayPlan days={days} />
          {state.bookings &&
            Object.values(state.bookings).some((b) => b.id !== receipt?.id) && (
              <details className="past-orders">
                <summary>
                  Сохранённые имитационные заказы (
                  {
                    Object.values(state.bookings).filter(
                      (b) => b.id !== receipt?.id,
                    ).length
                  }
                  )
                </summary>
                {Object.values(state.bookings)
                  .filter((b) => b.id !== receipt?.id)
                  .map((b) => (
                    <div key={b.id}>
                      <p>
                        № {b.id.slice(0, 8)} · версия {b.revision} ·{" "}
                        {money(b.payment?.amount)} · имитация
                      </p>
                      {b.items?.map((item) => (
                        <p key={item.source_id}>
                          {item.name} · {item.details?.start} —{" "}
                          {item.details?.end}
                        </p>
                      ))}
                      <DayPlan days={b.itinerary || []} />
                    </div>
                  ))}
              </details>
            )}
        </>
      )}
    </div>
  );
}

function Planner({
  state,
  tripId,
  busy,
  choose,
  back,
  pay,
  navigate,
  download,
}) {
  const index = stages.indexOf(state?.stage || "scenarios");
  const titles = [
    "Сначала — настроение",
    "Как доберёмся?",
    "Где будем просыпаться?",
    "Дни, которые запомнятся",
    "Осталось проверить детали",
    "Всё важное — с вами",
  ];
  const descriptions = [
    "Выберите то, что откликается. Детали соберём дальше.",
    "Сравните варианты и выберите удобный. Отель подберём следующим.",
    "Ваше место силы на время поездки.",
    "Места рядом с вашим отелем и время просто пожить.",
    "Билеты, проживание и программа в одном плане.",
    "Маршрут, детали заказа и помощь в пути.",
  ];
  return (
    <section className="planner">
      <nav className="stepper" aria-label="Шаги поездки">
        {stageNames.slice(0, 5).map((name, i) => (
          <button
            disabled={busy || i >= index}
            className={`${i < index ? "done" : ""} ${i === index ? "current" : ""}`}
            key={name}
            onClick={() => back(stages[i])}
          >
            <span>{i < index ? <Check size={13} /> : i + 1}</span>
            <small>{name}</small>
          </button>
        ))}
      </nav>
      <div className="planner-head">
        <div>
          <div className="eyebrow">
            {index === 5 ? "ВАША ПОЕЗДКА" : `ШАГ ${index + 1} ИЗ 5`}
          </div>
          <h1>{titles[index]}</h1>
          <p>{descriptions[index]}</p>
        </div>
        {index > 0 && (
          <button
            className="text-button"
            disabled={busy}
            onClick={() => back(stages[index - 1])}
          >
            <ArrowLeft size={15} />
            Назад
          </button>
        )}
      </div>
      {state?.constraints?.start && (
        <div className="trip-pills">
          <span>
            <MapPin size={14} />
            {state.constraints.destination}
          </span>
          <span>
            <CalendarDays size={14} />
            {date(state.constraints.start)} — {date(state.constraints.end)}
          </span>
          <span>
            <Users size={14} />
            {state.constraints.adults || "—"} взрослых
          </span>
          {state.constraints.budget && (
            <span>
              <Wallet size={14} />
              до {money(state.constraints.budget)}{" "}
              {state.constraints.budget_basis === "person"
                ? "/ чел."
                : "на всех"}
            </span>
          )}
        </div>
      )}
      {state?.pending_check_in && (
        <div className="notice warning">
          <CalendarDays size={20} />
          <span>
            Прилёт {date(state.pending_check_in)}. Обсудите с ассистентом новую
            дату заселения и подтвердите её в чате.
          </span>
        </div>
      )}
      {state?.notice && (
        <div className="notice">
          <LifeBuoy size={19} />
          <span>{state.notice}</span>
        </div>
      )}
      {index < 3 ? (
        <div
          className={`choices-grid ${index === 0 ? "scenarios-grid" : "offers-grid"}`}
        >
          {state?.choices?.map((choice, i) => (
            <ChoiceCard
              key={choice.id}
              choice={choice}
              index={i}
              state={state}
              choose={choose}
              busy={busy}
            />
          ))}
        </div>
      ) : index === 3 ? (
        <>
          <DayPlan days={currentOption(state)?.days || []} />
          {state.choices?.map((c) => (
            <button
              key={c.id}
              className="primary approve-program"
              disabled={busy}
              onClick={() => choose(c.id)}
            >
              Программа мне подходит
              <ArrowRight size={18} />
            </button>
          ))}
        </>
      ) : (
        <Summary
          state={state}
          tripId={tripId}
          pay={pay}
          navigate={navigate}
          download={download}
          expanded
        />
      )}
      {index < 4 && !state?.choices?.length && !busy && (
        <div className="empty-state">
          <span className="empty-icon">
            <MessageCircle size={33} />
          </span>
          <h3>
            {state?.status === "error"
              ? "Попробуем ещё раз"
              : "Хорошая поездка начинается с деталей"}
          </h3>
          <p>
            {state?.answer ||
              "Расскажите ассистенту о вашем отдыхе. Варианты появятся здесь, шаг за шагом."}
          </p>
        </div>
      )}
      {busy && (
        <div className="searching">
          <div className="search-orbit">
            <Plane size={28} />
          </div>
          <h3>Ищем ваше «вот оно»</h3>
          <p>
            Проверяем источники и собираем детали.
            <br />
            Иногда на это нужно несколько минут.
          </p>
          <div className="shimmer-line" />
        </div>
      )}
      <div className="planner-bottom">
        <ShieldCheck size={15} />
        Выбор за вами. Бронирование и оплата — имитация.
      </div>
    </section>
  );
}

function Payment({ close, state, account, book, busy }) {
  const [method, setMethod] = useState("card");
  const [accepted, setAccepted] = useState(false);
  const [contact, setContact] = useState(account.email || "");
  const [payer, setPayer] = useState(account.name || "");
  const option = currentOption(state);
  return (
    <Modal wide title="И всё — можно собирать чемодан" close={close}>
      <div className="payment-layout">
        <div>
          <span className="eyebrow">1. КОНТАКТНЫЕ ДАННЫЕ</span>
          <p className="small muted">
            Используются для демонстрации формы и не передаются поставщикам.
          </p>
          <label className="field-label">
            Имя путешественника
            <input
              value={payer}
              onChange={(e) => setPayer(e.target.value)}
              maxLength={80}
              required
            />
          </label>
          <label className="field-label">
            Email для маршрута
            <input
              value={contact}
              onChange={(e) => setContact(e.target.value)}
              type="email"
              maxLength={254}
              required
            />
          </label>
          <span className="eyebrow payment-label">2. СПОСОБ ОПЛАТЫ</span>
          <div className="payment-methods">
            <button
              className={method === "card" ? "selected" : ""}
              onClick={() => setMethod("card")}
            >
              <CreditCard size={18} />
              <strong>Карта</strong>
              <small>Демо •••• 4242</small>
            </button>
            <button
              className={method === "sbp" ? "selected" : ""}
              onClick={() => setMethod("sbp")}
            >
              <Wallet size={18} />
              <strong>СБП</strong>
              <small>Имитация</small>
            </button>
          </div>
          <div className="demo-card">
            <span>О! рядом</span>
            <span>DEMO</span>
            <strong>
              {method === "card"
                ? "••••  ••••  ••••  4242"
                : "Система быстрых путешествий"}
            </strong>
            <small>Тестовый способ оплаты · 0 реальных списаний</small>
          </div>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={accepted}
              onChange={(e) => setAccepted(e.target.checked)}
            />
            Я понимаю, что это имитация: деньги не спишутся, реальные билеты и
            отель не бронируются.
          </label>
        </div>
        <div className="payment-order">
          <span className="eyebrow">ВАША ПОЕЗДКА</span>
          <h3>{state.constraints.destination}</h3>
          <p>
            {date(state.constraints.start)} — {date(state.constraints.end)}
          </p>
          <div>
            <Plane size={17} />
            <span>{option?.transport?.name}</span>
          </div>
          <div>
            <Building2 size={17} />
            <span>{option?.stay?.name}</span>
          </div>
          <hr />
          <div className="order-total">
            <span>За всех</span>
            <strong>{money(option?.budget?.known_subtotal)}</strong>
          </div>
          <p className="small muted">
            Только известная стоимость билетов и проживания. Другие расходы
            уточняются.
          </p>
          <button
            className="primary"
            disabled={
              busy ||
              !accepted ||
              !payer.trim() ||
              !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(contact)
            }
            onClick={() => book(method)}
          >
            {busy ? (
              <LoaderCircle size={18} className="spin" />
            ) : (
              <LockKeyhole size={17} />
            )}
            Оплатить · имитация
          </button>
          <span className="payment-secure">
            <ShieldCheck size={14} />
            Данные банковской карты не нужны
          </span>
        </div>
      </div>
    </Modal>
  );
}

function Profile({ account, setAccount, run, auth, logout }) {
  const [link, setLink] = useState(null);
  const [remove, setRemove] = useState(false);
  const [deletion, setDeletion] = useState("");
  const [saving, setSaving] = useState(false);
  if (!account) return <AccountRequired auth={auth} />;
  async function save(e) {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.currentTarget));
    data.interests = data.interests
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    setSaving(true);
    await run(async () => {
      setAccount(await api("/api/account", { method: "PUT", body: data }));
    });
    setSaving(false);
  }
  return (
    <div className="page narrow-page">
      <div className="page-title">
        <div className="eyebrow">ПУТЕШЕСТВИЯ НАЧИНАЮТСЯ С ВАС</div>
        <h1>Личный кабинет</h1>
        <p>Немного о вас — для поездок, которые подходят именно вам.</p>
      </div>
      <div className="profile-grid">
        <section className="surface">
          <div className="profile-intro">
            <span className="profile-avatar">{account.name[0]}</span>
            <div>
              <h3>{account.name}</h3>
              <span className="muted">
                {account.email || "Аккаунт Telegram"}
              </span>
            </div>
          </div>
          <form className="form" onSubmit={save}>
            <label>
              Имя
              <input
                name="name"
                defaultValue={account.name}
                required
                maxLength={80}
                autoComplete="given-name"
              />
            </label>
            <div className="form-row">
              <label>
                Город отправления
                <input
                  name="city"
                  defaultValue={account.city}
                  maxLength={100}
                  autoComplete="address-level2"
                  placeholder="Москва"
                />
              </label>
              <label>
                Телефон
                <input
                  name="phone"
                  defaultValue={account.phone}
                  maxLength={30}
                  type="tel"
                  autoComplete="tel"
                  placeholder="+7"
                />
              </label>
            </div>
            <label>
              Что любите в путешествиях
              <input
                name="interests"
                defaultValue={account.interests.join(", ")}
                placeholder="Море, прогулки, местная кухня"
                maxLength={1000}
              />
              <span className="small muted">
                До 10 интересов через запятую. Учтём в новых поездках.
              </span>
            </label>
            <button className="primary" disabled={saving}>
              {saving ? (
                <LoaderCircle size={17} className="spin" />
              ) : (
                <Check size={17} />
              )}
              Сохранить изменения
            </button>
          </form>
        </section>
        <aside>
          <section className="telegram-surface">
            <span className="telegram-big">
              <Send size={27} />
            </span>
            <h3>Рядом. Даже в Telegram.</h3>
            <p>
              Те же поездки и история — в привычном мессенджере. Свяжите
              аккаунты одноразовой ссылкой.
            </p>
            {account.telegram_linked ? (
              <>
                <span className="connected">
                  <CheckCircle2 size={16} />
                  Telegram подключён
                </span>
                <button
                  className="secondary"
                  onClick={() =>
                    run(async () => {
                      await api("/api/telegram/link", { method: "DELETE" });
                      setAccount(await api("/api/account"));
                      setLink(null);
                    })
                  }
                >
                  Отключить
                </button>
              </>
            ) : link ? (
              <>
                <a
                  href={link}
                  className="primary"
                  target="_blank"
                  rel="noreferrer"
                >
                  <Send size={16} />
                  Открыть и связать
                </a>
                <span className="small muted">
                  Ссылка действует 10 минут. Не передавайте её другим.
                </span>
                <button
                  className="text-button"
                  onClick={() =>
                    run(async () => setAccount(await api("/api/account")))
                  }
                >
                  Проверить подключение
                </button>
              </>
            ) : (
              <button
                className="primary"
                onClick={() =>
                  run(async () =>
                    setLink(
                      (await api("/api/telegram/link", { method: "POST" })).url,
                    ),
                  )
                }
              >
                <Link2 size={17} />
                Подключить Telegram
              </button>
            )}
          </section>
          <div className="profile-management">
            <button className="text-button" onClick={logout}>
              <LogOut size={16} />
              Выйти из аккаунта
            </button>
            <button
              className="text-button danger"
              onClick={() => setRemove(true)}
            >
              <Trash2 size={16} />
              Удалить аккаунт
            </button>
          </div>
        </aside>
      </div>
      {remove && (
        <Modal title="Удалить аккаунт?" close={() => setRemove(false)}>
          <p>
            Профиль, поездки, история диалогов и связь с Telegram будут удалены
            без возможности восстановления.
          </p>
          <label className="field-label">
            Введите УДАЛИТЬ для подтверждения
            <input
              value={deletion}
              onChange={(e) => setDeletion(e.target.value)}
            />
          </label>
          <button
            className="primary danger-button"
            disabled={deletion !== "УДАЛИТЬ"}
            onClick={() =>
              run(async () => {
                await api("/api/account", {
                  method: "DELETE",
                  body: { confirmation: deletion },
                });
                setAccount(null);
                window.location.hash = "plan";
              })
            }
          >
            Удалить мои данные
          </button>
        </Modal>
      )}
    </div>
  );
}

function AccountRequired({ auth }) {
  return (
    <div className="empty-state account-required">
      <span className="empty-icon">
        <CircleUserRound size={34} />
      </span>
      <h1>Ваши путешествия будут здесь</h1>
      <p>
        Войдите или создайте аккаунт, чтобы сохранять планы и продолжать в любой
        момент.
      </p>
      <button className="primary" onClick={auth}>
        Войти или зарегистрироваться
        <ArrowRight size={17} />
      </button>
    </div>
  );
}

function Trips({ account, auth, trips, navigate, reload, run }) {
  const [filter, setFilter] = useState("all");
  if (!account) return <AccountRequired auth={auth} />;
  const filtered = trips.filter(
    (t) =>
      filter === "all" ||
      (filter === "plans"
        ? t.state.stage !== "booked"
        : t.state.stage === "booked"),
  );
  return (
    <div className="page">
      <div className="page-title row-title">
        <div>
          <div className="eyebrow">ВАШИ ЛИЧНЫЕ ИСТОРИИ</div>
          <h1>Мои поездки</h1>
          <p>Мечты, планы и места, куда хочется вернуться.</p>
        </div>
        <button className="primary" onClick={() => navigate("plan")}>
          <Plus size={18} />
          Новая поездка
        </button>
      </div>
      <div className="trips-toolbar">
        <div className="tabs">
          {[
            ["all", "Все поездки"],
            ["plans", "Планируем"],
            ["booked", "Собраны"],
          ].map(([id, title]) => (
            <button
              className={filter === id ? "active" : ""}
              key={id}
              onClick={() => setFilter(id)}
            >
              {title}
            </button>
          ))}
        </div>
        <button className="text-button" onClick={() => run(reload)}>
          <History size={16} />
          Обновить
        </button>
      </div>
      {filtered.length ? (
        <div className="trips-grid">
          {filtered.map((t) => (
            <button
              className="history-card"
              key={t.trip_id}
              onClick={() =>
                navigate(
                  t.state.stage === "booked" ? "trip" : "plan",
                  t.trip_id,
                )
              }
            >
              <div className="history-photo">
                <img
                  src={`/images/${/Полян|Хутор/.test(t.state.constraints?.destination) ? "mountains" : "sea"}.jpg`}
                  alt=""
                />
                <span className="image-pill">{tripStatus(t.state)}</span>
                <span className="history-step">
                  {stageNames[stages.indexOf(t.state.stage || "scenarios")]}
                </span>
              </div>
              <div className="history-content">
                <span className="eyebrow">
                  {t.state.stage === "booked"
                    ? "ВАШЕ ПУТЕШЕСТВИЕ"
                    : "ПРОДОЛЖИМ ПЛАНИРОВАТЬ?"}
                </span>
                <h3>{t.state.constraints?.destination || "Новая история"}</h3>
                <p>
                  <CalendarDays size={15} />
                  {date(t.state.constraints?.start)}
                  {t.state.constraints?.end
                    ? ` — ${date(t.state.constraints.end)}`
                    : ""}
                </p>
                <div>
                  <span>
                    {t.state.constraints?.adults
                      ? `${t.state.constraints.adults} взрослых`
                      : "Детали уточняются"}
                  </span>
                  <span className="history-open">
                    <ArrowUpRight size={20} />
                  </span>
                </div>
              </div>
            </button>
          ))}
        </div>
      ) : (
        <div className="empty-state">
          <span className="empty-icon">
            <Luggage size={34} />
          </span>
          <h3>
            {trips.length
              ? "Пока нет поездок в этой категории"
              : "Первая поездка — впереди"}
          </h3>
          <p>Расскажите ассистенту, какой отдых вам хочется.</p>
          <button className="primary" onClick={() => navigate("plan")}>
            Спланировать поездку
            <ArrowRight size={17} />
          </button>
        </div>
      )}
    </div>
  );
}

function Support({ guides, tripId, run, discuss }) {
  const [letter, setLetter] = useState(null);
  const [copied, setCopied] = useState(false);
  async function open(g) {
    setCopied(false);
    if (tripId)
      await run(async () =>
        setLetter(await api(`/trips/${tripId}/support/${g.id}`)),
      );
    else setLetter(g);
  }
  return (
    <div className="page narrow-page">
      <div className="support-hero">
        <span className="support-icon">
          <LifeBuoy size={30} />
        </span>
        <div className="eyebrow">КОГДА ПЛАНЫ МЕНЯЮТСЯ</div>
        <h1>Мы рядом. Разберёмся.</h1>
        <p>
          Понятные шаги и готовые письма — чтобы неожиданности
          <br />
          не забирали всё внимание.
        </p>
      </div>
      <div className="support-grid">
        {guides.map((g, i) => (
          <button className="support-card" key={g.id} onClick={() => open(g)}>
            <span className={`support-card-icon tone-${i}`}>
              <Icon of={[Plane, Building2, Luggage, Mail][i]} size={26} />
            </span>
            <h3>{g.title}</h3>
            <p>{g.description}</p>
            <span className="text-link">
              Что делать
              <ArrowUpRight size={17} />
            </span>
          </button>
        ))}
      </div>
      <div className="support-bottom">
        <MessageCircle size={25} />
        <div>
          <h3>Ваша ситуация немного другая?</h3>
          <p>Обсудите её с ассистентом в чате поездки.</p>
        </div>
        <button
          className="secondary"
          onClick={() =>
            discuss("Помоги разобраться с неожиданной ситуацией в поездке")
          }
        >
          Обсудить
          <ArrowRight size={16} />
        </button>
      </div>
      <p className="demo-note">
        Справочник помогает подготовить обращение. Актуальные условия уточняйте
        у поставщика.
      </p>
      {letter && (
        <Modal wide title={letter.title} close={() => setLetter(null)}>
          <ol className="support-steps">
            {letter.steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
          <div className="letter-head">
            <h3>Черновик письма</h3>
            <button
              className="secondary"
              onClick={() =>
                run(async () => {
                  await navigator.clipboard.writeText(
                    `Тема: ${letter.subject}\n\n${letter.letter}`,
                  );
                  setCopied(true);
                })
              }
            >
              {copied ? <Check size={15} /> : <Copy size={15} />}
              {copied ? "Скопировано" : "Скопировать"}
            </button>
          </div>
          <div className="letter">
            <strong>Тема: {letter.subject}</strong>
            <p>{letter.letter}</p>
          </div>
          <p className="small muted">
            Заполните поля в скобках и проверьте факты. Письмо не отправлено.
          </p>
          <button
            className="text-button"
            onClick={() => {
              setLetter(null);
              discuss(`Помоги составить письмо: ${letter.title}`);
            }}
          >
            <MessageCircle size={16} />
            Обсудить с ассистентом
          </button>
        </Modal>
      )}
    </div>
  );
}

function Tracking({
  state,
  tripId,
  progress,
  setProgress,
  run,
  discuss,
  download,
}) {
  const items = progress?.items || [];
  const completed = progress?.completed || {};
  const done = items.filter((i) => completed[i.id]).length;
  const days =
    state.stage === "booked"
      ? state.receipt?.itinerary
      : currentOption(state)?.days;
  const [saving, setSaving] = useState(false);
  async function toggle(id) {
    if (saving) return;
    setSaving(true);
    await run(async () => {
      const current = Object.fromEntries(
        items.map((i) => [i.id, !!completed[i.id]]),
      );
      setProgress(
        await api(`/trips/${tripId}/progress`, {
          method: "PUT",
          body: { completed: { ...current, [id]: !completed[id] } },
        }),
      );
    });
    setSaving(false);
  }
  return (
    <div className="page narrow-page">
      <div className="tracking-banner">
        <div>
          <span className="eyebrow">{tripStatus(state).toUpperCase()}</span>
          <h1>Хорошо, когда всё под рукой.</h1>
          <p>
            {state.constraints?.destination} · {date(state.constraints?.start)}{" "}
            — {date(state.constraints?.end)}
          </p>
          <button className="secondary" onClick={download}>
            <Download size={17} />
            Маршрут PDF
          </button>
        </div>
        <span className="tracking-illustration">
          <Compass size={100} strokeWidth={0.8} />
        </span>
      </div>
      <div className="tracking-grid">
        <section className="surface">
          <div className="section-heading">
            <h2>До старта</h2>
            <span className="muted">
              {done} / {items.length}
            </span>
          </div>
          <div className="progress-track">
            <span
              style={{
                width: `${items.length ? (done / items.length) * 100 : 0}%`,
              }}
            />
          </div>
          {items
            .filter((i) => !i.date)
            .map((i) => (
              <label className="checklist-item" key={i.id}>
                <input
                  disabled={saving}
                  type="checkbox"
                  checked={!!completed[i.id]}
                  onChange={() => toggle(i.id)}
                />
                <span>{i.title}</span>
              </label>
            ))}
          <h2 className="subheading">Ваши дни</h2>
          <DayPlan days={days || []} completed={completed} toggle={toggle} />
        </section>
        <aside className="tracking-aside">
          <section className="surface">
            <span className="support-icon">
              <LifeBuoy size={24} />
            </span>
            <h3>Что-то пошло не по плану?</h3>
            <p>Поможем разобраться, составить письмо или обсудить изменения.</p>
            <button
              className="primary"
              onClick={() => (window.location.hash = `support/${tripId}`)}
            >
              <LifeBuoy size={17} />
              Открыть справочник
            </button>
            <button
              className="secondary"
              onClick={() => discuss("Помоги составить письмо в отель")}
            >
              <MessageCircle size={17} />
              Написать ассистенту
            </button>
          </section>
          <section className="telegram-surface">
            <Send size={25} />
            <h3>Возьмите нас с собой</h3>
            <p>
              Подключите Telegram в профиле — и продолжайте эту же поездку в
              боте.
            </p>
            <a className="text-link" href="#profile">
              Подключить
              <ArrowUpRight size={17} />
            </a>
          </section>
          <p className="small muted">
            Отметки сохраняются в вашем аккаунте. Статусы рейсов проверяйте у
            перевозчика: автоматического мониторинга здесь нет.
          </p>
        </aside>
      </div>
    </div>
  );
}

function App() {
  const [route, setRoute] = useState(
    () => window.location.hash.slice(1) || "plan",
  );
  const [account, setAccount] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [auth, setAuth] = useState(false);
  const [state, setState] = useState(null);
  const [trips, setTrips] = useState([]);
  const [guides, setGuides] = useState([]);
  const [progress, setProgress] = useState(null);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [payment, setPayment] = useState(false);
  const [mobileChat, setMobileChat] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [page, tripId] = route.split("/");
  const operation = useRef(false);
  const navigate = (page, id) => {
    window.location.hash = page + (id ? "/" + id : "");
    setMobileNav(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  useEffect(() => {
    const update = () => setRoute(window.location.hash.slice(1) || "plan");
    window.addEventListener("hashchange", update);
    const loginToken = window.location.hash.startsWith("#login/")
      ? window.location.hash.slice(7)
      : null;
    (loginToken
      ? api("/api/auth/telegram", {
          method: "POST",
          body: { token: loginToken },
        })
      : api("/api/account")
    )
      .then((data) => {
        setAccount(data);
        if (loginToken) {
          window.history.replaceState(null, "", "#trips");
          setRoute("trips");
        }
      })
      .catch((e) => {
        if (e.status !== 401 || loginToken) setError(e.message);
        if (loginToken) {
          window.history.replaceState(null, "", "#plan");
          setRoute("plan");
        }
      })
      .finally(() => setAuthChecked(true));
    api("/api/support")
      .then(setGuides)
      .catch((e) => setError(e.message));
    return () => window.removeEventListener("hashchange", update);
  }, []);
  const reloadTrips = async () => setTrips(await api("/trips"));
  useEffect(() => {
    let active = true;
    if (!account) {
      setTrips([]);
      setState(null);
      return;
    }
    api("/trips")
      .then((t) => {
        if (active) setTrips(t);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [account]);
  useEffect(() => {
    let active = true;
    setState(null);
    setProgress(null);
    if (!tripId || !account) return;
    setLoading(true);
    api(`/trips/${tripId}`)
      .then((s) => {
        if (active) setState(s);
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    if (page === "track")
      api(`/trips/${tripId}/progress`)
        .then((p) => {
          if (active) setProgress(p);
        })
        .catch((e) => {
          if (active) setError(e.message);
        });
    return () => {
      active = false;
    };
  }, [tripId, page, account?.id]);
  useEffect(() => {
    if (!error && !success) return;
    const timeout = setTimeout(() => {
      setError("");
      setSuccess("");
    }, 8000);
    return () => clearTimeout(timeout);
  }, [error, success]);
  async function run(fn) {
    setError("");
    try {
      return await fn();
    } catch (e) {
      setError(
        e.message || "Не удалось связаться с сервером. Проверьте соединение.",
      );
      if (e.status === 401) setAuth(true);
      if ([409, 504].includes(e.status) && tripId) {
        try {
          setState(await api(`/trips/${tripId}`));
        } catch {}
      }
      return null;
    }
  }
  async function mutate(fn) {
    if (operation.current) return;
    operation.current = true;
    setBusy(true);
    await run(fn);
    setBusy(false);
    operation.current = false;
  }
  async function send() {
    if (!value.trim() || operation.current) return;
    if (!account) {
      setAuth(true);
      return;
    }
    const text = value.trim();
    await mutate(async () => {
      let id = tripId;
      if (!id) {
        id = (await api("/trips", { method: "POST" })).trip_id;
        navigate("plan", id);
      }
      const current =
        id === tripId && state ? state : await api(`/trips/${id}`);
      const startRoute = "plan/" + id;
      const next = await api(`/trips/${id}/messages`, {
        method: "POST",
        body: { message: text, revision: current.revision },
      });
      if (window.location.hash.slice(1) === startRoute) {
        setState(next);
        setMobileChat(next.status === "needs_input" && !next.choices?.length);
      }
      setValue("");
      await reloadTrips();
    });
  }
  const choose = (id) =>
    mutate(async () => {
      const next = await api(
        `/trips/${tripId}/select/${encodeURIComponent(id)}?revision=${state.revision}`,
        { method: "POST" },
      );
      if (window.location.hash.slice(1) === "plan/" + tripId) {
        setState(next);
        setMobileChat(next.status === "needs_input" && !next.choices?.length);
      }
      await reloadTrips();
    });
  const back = (stage) =>
    mutate(async () => {
      const next = await api(`/trips/${tripId}/back`, {
        method: "POST",
        body: { stage, revision: state.revision },
      });
      if (window.location.hash.slice(1) === "plan/" + tripId) setState(next);
      await reloadTrips();
    });
  const download = () =>
    run(async () => {
      const response = await fetch(`/trips/${tripId}/itinerary.pdf`, {
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error("Сначала составьте программу поездки.");
      const url = URL.createObjectURL(await response.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = "Мой маршрут — О! рядом.pdf";
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  const book = (method) =>
    mutate(async () => {
      await api(`/trips/${tripId}/bookings`, {
        method: "POST",
        body: {
          option_id: state.selected,
          revision: state.revision,
          confirm: true,
          idempotency_key: `checkout-${state.revision}-${state.selected}`,
          payment_method: method,
        },
      });
      setState(await api(`/trips/${tripId}`));
      setPayment(false);
      setSuccess(
        "Поездка сохранена. Можно предвкушать! Оплата была имитацией.",
      );
      await reloadTrips();
      navigate("trip", tripId);
    });
  const discuss = (text) => {
    setValue(text);
    navigate("plan", tripId);
    setMobileChat(true);
  };
  const logout = () =>
    run(async () => {
      await api("/api/auth/logout", { method: "POST" });
      setAccount(null);
      setState(null);
      navigate("plan");
    });
  const planning = page === "plan" && !!tripId && !!account;
  return (
    <>
      <header className="header">
        <div className="header-inner">
          <Brand />
          <nav className={mobileNav ? "nav mobile-open" : "nav"}>
            <a className={page === "plan" ? "active" : ""} href="#plan">
              <Sparkles size={16} />
              Спланировать
            </a>
            <a
              className={
                page === "trips" || page === "trip" || page === "track"
                  ? "active"
                  : ""
              }
              href="#trips"
            >
              Мои поездки
            </a>
            <a
              className={page === "support" ? "active" : ""}
              href={tripId ? `#support/${tripId}` : "#support"}
            >
              Помощь в пути
            </a>
          </nav>
          <div className="header-actions">
            <TelegramLink className="telegram-link" />
            <button
              className="account-button"
              onClick={() => (account ? navigate("profile") : setAuth(true))}
            >
              <CircleUserRound size={19} />
              <span>{account?.name || "Войти"}</span>
            </button>
            <button
              className="mobile-menu icon-button"
              onClick={() => setMobileNav(!mobileNav)}
              aria-label="Открыть меню"
            >
              <Menu size={22} />
            </button>
          </div>
        </div>
      </header>
      <main className={planning ? "workspace-main" : "main"}>
        {page === "login" ? (
          <div className="page-loading">
            <LoaderCircle className="spin" />
            Открываем ваши поездки…
          </div>
        ) : planning ? (
          <>
            <div className="workspace-top">
              <a href="#trips">
                <ArrowLeft size={14} />
                Мои поездки
              </a>
              <span>
                <MapPin size={13} />
                {state?.constraints?.destination || "Большой Сочи"}
              </span>
              <button
                className="text-button"
                disabled={busy}
                onClick={() =>
                  run(async () => setState(await api(`/trips/${tripId}`)))
                }
              >
                Обновить поездку
              </button>
            </div>
            <div className="mobile-switch">
              <button
                className={mobileChat ? "active" : ""}
                onClick={() => setMobileChat(true)}
              >
                <MessageCircle size={16} />
                Диалог
              </button>
              <button
                className={!mobileChat ? "active" : ""}
                onClick={() => setMobileChat(false)}
              >
                <Route size={16} />
                План поездки
              </button>
            </div>
            <div
              className={`workspace ${mobileChat ? "show-chat" : "show-plan"}`}
            >
              <Chat
                state={state}
                value={value}
                setValue={setValue}
                send={send}
                busy={busy}
                newTrip={() => navigate("plan")}
              />
              {loading ? (
                <div className="page-loading">
                  <LoaderCircle className="spin" />
                  Возвращаемся к вашей поездке…
                </div>
              ) : state ? (
                <Planner
                  state={state}
                  tripId={tripId}
                  busy={busy}
                  choose={(id) => {
                    setMobileChat(false);
                    choose(id);
                  }}
                  back={back}
                  pay={() => setPayment(true)}
                  navigate={navigate}
                  download={download}
                />
              ) : (
                <div className="empty-state">
                  <h3>Не удалось открыть поездку</h3>
                  <a href="#trips">К моим поездкам</a>
                </div>
              )}
            </div>
          </>
        ) : page === "trips" ? (
          <Trips
            account={account}
            auth={() => setAuth(true)}
            trips={trips}
            navigate={navigate}
            run={run}
            reload={reloadTrips}
          />
        ) : page === "profile" ? (
          <Profile
            account={account}
            setAccount={(data) => {
              setAccount(data);
              setSuccess(data ? "Изменения сохранены" : "Аккаунт удалён");
            }}
            run={run}
            auth={() => setAuth(true)}
            logout={logout}
          />
        ) : page === "support" ? (
          <Support
            guides={guides}
            tripId={tripId}
            run={run}
            discuss={discuss}
          />
        ) : ["trip", "track"].includes(page) && tripId ? (
          !account && authChecked ? (
            <AccountRequired auth={() => setAuth(true)} />
          ) : loading || !authChecked ? (
            <div className="page-loading">
              <LoaderCircle className="spin" />
              Открываем путешествие…
            </div>
          ) : !state ? (
            <div className="empty-state">
              <h3>Не удалось открыть поездку</h3>
              <a className="primary" href="#trips">
                К моим поездкам
              </a>
            </div>
          ) : page === "track" ? (
            <Tracking
              state={state}
              tripId={tripId}
              progress={progress}
              setProgress={setProgress}
              run={run}
              discuss={discuss}
              download={download}
            />
          ) : (
            <div className="page summary-page">
              <div className="summary-page-top">
                <a className="text-button" href="#trips">
                  <ArrowLeft size={15} />
                  Мои поездки
                </a>
                <button
                  className="text-button"
                  onClick={() => navigate("plan", tripId)}
                >
                  <MessageCircle size={16} />
                  Обсудить с ассистентом
                </button>
              </div>
              <Summary
                state={state}
                tripId={tripId}
                pay={() => setPayment(true)}
                navigate={navigate}
                download={download}
                expanded
              />
            </div>
          )
        ) : (
          <Home
            value={value}
            setValue={setValue}
            send={send}
            busy={busy}
            user={account}
          />
        )}
      </main>
      {!planning && (
        <footer>
          <Brand />
          <span>Хорошие путешествия начинаются с разговора.</span>
          <TelegramLink className="footer-telegram" />
        </footer>
      )}
      {auth && (
        <Auth
          close={() => setAuth(false)}
          authenticated={setAccount}
          run={run}
        />
      )}
      {payment && state && (
        <Payment
          close={() => {
            if (!busy) setPayment(false);
          }}
          state={state}
          account={account}
          book={book}
          busy={busy}
        />
      )}
      {(error || success) && (
        <div
          className={`toast ${error ? "toast-error" : ""}`}
          role={error ? "alert" : "status"}
        >
          {error ? <LifeBuoy size={19} /> : <CheckCircle2 size={19} />}
          <span>{error || success}</span>
          <button
            className="icon-button"
            onClick={() => {
              setError("");
              setSuccess("");
            }}
            aria-label="Скрыть уведомление"
          >
            <X size={17} />
          </button>
        </div>
      )}
    </>
  );
}

createRoot(document.getElementById("root")).render(<App />);
