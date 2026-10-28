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
  TrainFront,
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
  Maximize2,
  PanelRightOpen,
  Columns2,
  List,
  FolderOpen,
} from "lucide-react";
import {
  stages,
  stageNames,
  money,
  date,
  time,
  basis,
  party,
  safeUrl,
  currentOption,
  tripParts,
  tripMapPoints,
  tripMapUrls,
  tripStatus,
  canCheckout,
  messageLinks,
  transportRoutes,
  pendingText,
  offerItems,
  offerChoice,
  offerSelected,
  counted,
} from "./format";
import "./styles.css";

const TELEGRAM = "https://t.me/ostrovok_helper_ryadom_bot";
function DestinationExplorer({ onSelect }) {
  const [destinations, setDestinations] = useState([]);
  const [query, setQuery] = useState("");
  const [theme, setTheme] = useState("");
  const [expanded, setExpanded] = useState(false);
  useEffect(() => { let active = true; api("/api/destinations").then((items) => { if (active) setDestinations(items); }).catch(() => {}); return () => { active = false; }; }, []);
  const filtered = destinations.filter((item) => (!theme || item.theme === theme) && `${item.name} ${item.theme}`.toLocaleLowerCase("ru").includes(query.toLocaleLowerCase("ru")));
  return <section className="destination-explorer" aria-label="Направления России">
    <h2>Куда хочется отправиться?</h2>
    <p>Города, курорты и природа по всей России. Можно назвать любое другое направление.</p>
    <input type="search" aria-label="Найти направление" placeholder="Найти город или формат отдыха…" value={query} onChange={(event) => setQuery(event.target.value)} />
    <div className="destination-themes"><button className={!theme ? "active" : ""} onClick={() => setTheme("")}>Все направления</button>
      {[...new Set(destinations.map((item) => item.theme))].map((value) => <button key={value} className={theme === value ? "active" : ""} onClick={() => setTheme(value)}>{value}</button>)}
    </div>
    <div className="destination-chips">{(expanded || query || theme ? filtered : filtered.slice(0, 21)).map((item) => <button key={item.name} title={item.theme} onClick={() => onSelect(`Хочу поехать в ${item.name}. Помоги подобрать поездку с учётом моих пожеланий.`)}><MapPin size={13} />{item.name}</button>)}</div>
    {!expanded && !query && !theme && destinations.length > 21 && <button className="text-button" onClick={() => setExpanded(true)}>Показать все {destinations.length} направлений</button>}
    {query && !filtered.length && <p>Этого города нет среди примеров — его всё равно можно указать в запросе.</p>}
  </section>;
}

const inspiration = [
  {
    title: "В ритме моря",
    place: "Балтика · Чёрное море · Приморье",
    image: "sea",
    icon: Waves,
    text: "Хочу к морю в России. Сравни Калининградскую область, Чёрное море и Приморье: прогулки, вкусная еда и отель у воды",
  },
  {
    title: "Выше только облака",
    place: "Кавказ · Алтай · Камчатка",
    image: "mountains",
    icon: Mountain,
    text: "Хочу в горы: сравни Архыз, Домбай, Алтай и Шерегеш. Нужны красивые виды и уютный отель",
  },
  {
    title: "Всё и чуть больше",
    place: "Россия",
    image: "cable",
    icon: Compass,
    text: "Хочу путешествие по России, направление ещё не выбрал. Предложи 6–8 разных городов и объясни, кому какой подойдёт",
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

function Modal({ title, children, close, wide = false, className = "" }) {
  const ref = useRef(null);
  const closeRef = useRef(close);
  closeRef.current = close;
  useEffect(() => {
    const dialog = ref.current;
    dialog.showModal();
    const stop = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        closeRef.current();
      }
    };
    dialog.addEventListener("keydown", stop);
    return () => dialog.removeEventListener("keydown", stop);
  }, []);
  return (
    <dialog
      ref={ref}
      aria-label={title}
      className={`modal ${wide ? "modal-wide" : ""} ${className}`}
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

function Composer({ value, setValue, send, busy, compact = false, contextual = false }) {
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
          contextual ? "Задайте вопрос о поездке…" : compact
            ? "Что изменим? Например, отель поближе к морю…"
            : "Хочу на пять ночей вдвоём из Москвы. Сравни города России для прогулок, природы и вкусной еды…"
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
            ? contextual ? "Готовлю ответ…" : "Собираем ваши варианты…"
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

function TripMap({ state, preview = false }) {
  const [active, setActive] = useState(null);
  const [expanded, setExpanded] = useState(false);
  const points = tripMapPoints(state);
  const selected = points.find((point) => point.id === active);
  const urls = tripMapUrls(points, active);
  const title = preview ? "Море. Горы. И всё между ними." : "Ваша поездка на карте";
  const actions = (
    <div className="map-actions">
      {!expanded && (
        <button className="text-button" onClick={() => setExpanded(true)}>
          <Maximize2 size={15} /> Развернуть карту
        </button>
      )}
      <a className="text-button" href={urls.external} target="_blank" rel="noreferrer">
        Открыть в Яндекс Картах <ExternalLink size={14} />
      </a>
    </div>
  );
  const content = (
    <>
      <div className="map-canvas">
        <iframe src={urls.embed} title={selected ? `Карта: ${selected.name}` : "Яндекс Карты: места вашей поездки в России"}
          loading={expanded ? "eager" : "lazy"} allowFullScreen referrerPolicy="no-referrer" />
      </div>
      {points.length > 0 && (
        <div className="map-places" aria-label="Места поездки">
          <button aria-pressed={!selected} className={!selected ? "active" : ""} onClick={() => setActive(null)}>
            <MapPin size={14} /> Все места
          </button>
          {points.map((point) => (
            <button key={point.id} aria-pressed={selected?.id === point.id}
              className={selected?.id === point.id ? "active" : ""} onClick={() => setActive(point.id)}>
              <Icon of={point.kind === "transport" ? Plane : point.kind === "stay" ? Building2 : MapPin} size={14} />
              <span>{point.name}{point.approximate && <small> · район</small>}</span>
            </button>
          ))}
        </div>
      )}
      <p className="map-note" role="status">
        {selected
          ? `${selected.name} · ${selected.approximate ? "ориентир района, точный адрес не подтверждён" : "по координатам источника"}`
          : points.length ? "Выберите место, чтобы приблизить его на карте."
            : "Пока показана Россия. Места появятся, когда будут известны их координаты или район."}
        {!selected && points.some((point) => point.approximate) && " Метки «район» показывают приблизительное расположение."}
      </p>
    </>
  );
  return (
    <section className={`trip-map ${preview ? "map-preview" : ""}`} aria-label="Карта путешествия по России">
      <div className="map-caption">
        <span className="map-icon"><Route size={17} /></span>
        <div>
          <strong>{title}</strong>
          <span>{preview ? "Откройте своё направление в России" : "Отель и впечатления на Яндекс Картах"}</span>
        </div>
      </div>
      {expanded ? (
        <>
          <div className="map-expanded-placeholder">Карта открыта в большом окне</div>
          <Modal title={title} close={() => setExpanded(false)} wide className="map-modal">
            {actions}{content}
          </Modal>
        </>
      ) : <>{actions}{content}</>}
    </section>
  );
}

function Sidebar({
  account,
  state,
  trips,
  tripId,
  page,
  navigate,
  newTrip,
  auth,
  busy,
  open,
  close,
  openPanel,
  panelKind,
  chats = [],
  chatId,
  openChat,
  newChat,
  chatsError,
  reloadChats,
  removeChat,
}) {
  const [mobile, setMobile] = useState(
    () => window.matchMedia("(max-width: 760px)").matches,
  );
  const sidebar = useRef(null);
  useEffect(() => {
    const query = window.matchMedia("(max-width: 760px)");
    const update = () => {
      setMobile(query.matches);
      if (!query.matches) close();
    };
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (!open || !mobile) return;
    sidebar.current?.querySelector(".sidebar-close")?.focus();
    const escape = (event) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("keydown", escape);
    return () => {
      window.removeEventListener("keydown", escape);
      document.querySelector(".sidebar-toggle")?.focus();
    };
  }, [open, mobile]);
  const { transport, stay, days, total } = tripParts(state);
  const activeTrip = trips.find((trip) => trip.trip_id === tripId);
  const tracked =
    activeTrip?.state.stage === "booked"
      ? activeTrip
      : trips.find((trip) => trip.state.stage === "booked");
  const artifacts = [
    [Luggage, "Туры под ключ", state?.options?.length ? counted(state.options.length, "тур", "тура", "туров") : null, null, "tours"],
    [Plane, "Билеты", transport?.name, transport?.price, "transport"],
    [Building2, "Проживание", stay?.name, stay?.price, "stays"],
    [
      Route,
      "Программа",
      days.length ? `${counted(days.length, "день", "дня", "дней")} · ваш маршрут` : null,
      null,
      "itinerary",
    ],
    [Wallet, "Бюджет", total != null ? money(total) : null, null, "budget"],
  ].filter((item) => item[2] || (item[4] === "transport" || item[4] === "stays") && offerItems(state, item[4]).length);
  return (
    <>
      {open && (
        <button
          className="sidebar-backdrop"
          aria-label="Закрыть меню"
          onClick={close}
        />
      )}
      <aside
        ref={sidebar}
        inert={mobile && !open ? true : undefined}
        className={`app-sidebar ${open ? "is-open" : ""}`}
        aria-label="Основное меню"
      >
        <div className="sidebar-brand">
          <span onClick={close}>
            <Brand />
          </span>
          <button
            className="sidebar-close icon-button"
            aria-label="Закрыть меню"
            onClick={close}
          >
            <X size={21} />
          </button>
        </div>
        <button className="new-trip-button" onClick={newTrip}>
          <Plus size={18} /> Новая поездка <span>↗</span>
        </button>
        <nav className="sidebar-nav">
          <button
            className={page === "plan" ? "active" : ""}
            onClick={() => navigate("plan", tripId)}
          >
            <MessageCircle size={18} /> Диалог с агентом
          </button>
          <button
            className={["trips", "trip"].includes(page) ? "active" : ""}
            onClick={() => navigate("trips")}
          >
            <History size={18} /> Мои поездки
            {trips.length > 0 && <small>{trips.length}</small>}
          </button>
          <button
            className={page === "track" ? "active" : ""}
            onClick={() =>
              navigate(tracked ? "track" : "trips", tracked?.trip_id)
            }
          >
            <Compass size={18} /> В пути
          </button>
        </nav>
        <div className="sidebar-scroll">
          <div className="sidebar-section-title">
            {state?.autonomous && !state.selected && state.options?.length
              ? "ПРЕДПРОСМОТР ПОЕЗДКИ"
              : "В ВАШЕЙ ПОЕЗДКЕ"}{" "}
            <Luggage size={13} />
          </div>
          {artifacts.length ? (
            <div className="saved-artifacts">
              {artifacts.map(([Component, label, name, price, key]) => (
                <button key={key} className={page === "plan" && panelKind === key ? "artifact-active" : ""}
                  aria-expanded={page === "plan" && panelKind === key}
                  aria-controls="trip-options-panel" onClick={() => openPanel(key)}>
                  <span className={`artifact-icon artifact-${key}`}>
                    <Component size={18} />
                  </span>
                  <span>
                    <small>{label}</small>
                    <strong>{name || counted(offerItems(state, key).length, "вариант", "варианта", "вариантов")}</strong>
                    {price && (
                      <small>
                        {money(price.amount, price.currency)} ·{" "}
                        {basis(price.basis)}
                      </small>
                    )}
                  </span>
                  {state?.autonomous && !state.selected ? (
                    <ArrowUpRight size={13} />
                  ) : (
                    <Check size={13} />
                  )}
                </button>
              ))}
            </div>
          ) : (
            <div className="sidebar-artifact-empty">
              <span>
                <Plane size={17} />
                <Building2 size={17} />
                <Route size={17} />
              </span>
              <p>
                Билеты, отель и маршрут
                <br />
                сохранятся здесь по мере выбора.
              </p>
            </div>
          )}
          {tripId && <div className="trip-chat-folder">
            <div className="sidebar-section-title"><FolderOpen size={14} /> ЧАТЫ ПОЕЗДКИ
              <button className="icon-button" aria-label="Новый чат поездки" onClick={newChat}><Plus size={15} /></button>
            </div>
            <nav aria-label="Чаты поездки">
              <button className={page === "plan" && !chatId ? "active" : ""} onClick={() => openChat(null)}><Route size={15} /><span>План поездки</span></button>
              {chats.map((chat) => <div className="trip-chat-row" key={chat.chat_id}><button className={page === "plan" && chatId === chat.chat_id ? "active" : ""} onClick={() => openChat(chat.chat_id)}>
                <Icon of={chat.kind === "support" ? LifeBuoy : chat.kind === "places" ? MapPin : MessageCircle} size={15} /><span>{chat.title}</span>
              </button><button className="icon-button chat-delete" aria-label={`Удалить чат: ${chat.title}`} onClick={() => removeChat(chat)}><Trash2 size={13} /></button></div>)}
            </nav>
            {chatsError && <button className="text-button chat-retry" onClick={reloadChats}>Не удалось загрузить чаты · повторить</button>}
          </div>}
        </div>
        <div className="sidebar-bottom">
          <button
            className="sidebar-help"
            onClick={() => navigate("support", tripId)}
          >
            <LifeBuoy size={17} /> Помощь в пути <ArrowUpRight size={14} />
          </button>
          <TelegramLink className="sidebar-telegram">
            Продолжить в Telegram
          </TelegramLink>
          <button
            className="sidebar-account"
            onClick={() => (account ? navigate("profile") : auth())}
          >
            <span className="account-avatar">
              {account?.name?.[0] || <CircleUserRound size={20} />}
            </span>
            <span>
              <strong>{account?.name || "Личный кабинет"}</strong>
              <small>
                {account ? "Профиль и настройки" : "Войти и сохранить поездку"}
              </small>
            </span>
            <ChevronRight size={16} />
          </button>
        </div>
      </aside>
    </>
  );
}

function ChatInline({ text }) {
  return messageLinks(text).map((part, index) => part.href
    ? <a key={index} href={part.href} target="_blank" rel="noopener noreferrer">{part.text}</a>
    : <React.Fragment key={index}>{part.text.split(/(\*\*[^*\n]+\*\*|`[^`\n]+`)/g).map((token, i) =>
      token.startsWith("**") && token.endsWith("**") ? <strong key={i}>{token.slice(2, -2)}</strong>
        : token.startsWith("`") && token.endsWith("`") ? <code key={i}>{token.slice(1, -1)}</code>
          : <React.Fragment key={i}>{token}</React.Fragment>)}</React.Fragment>);
}

function ChatText({ text }) {
  const blocks = [];
  let paragraph = [], items = [], ordered = false;
  const flushParagraph = () => {
    if (paragraph.length) blocks.push(<p key={blocks.length}><ChatInline text={paragraph.join("\n")} /></p>);
    paragraph = [];
  };
  const flushList = () => {
    if (items.length) {
      const Tag = ordered ? "ol" : "ul";
      blocks.push(<Tag key={blocks.length}>{items.map((item, i) => <li key={i}><ChatInline text={item} /></li>)}</Tag>);
    }
    items = [];
  };
  for (const line of text.split("\n")) {
    const heading = line.match(/^#{1,3}\s+(.+)$/);
    const item = line.match(/^\s*(?:[-*•]|(\d+)\.)\s+(.+)$/);
    if (heading || !line.trim()) {
      flushParagraph(); flushList();
      if (heading) blocks.push(<h3 key={blocks.length}><ChatInline text={heading[1]} /></h3>);
    } else if (item) {
      flushParagraph();
      if (items.length && ordered !== !!item[1]) flushList();
      ordered = !!item[1]; items.push(item[2]);
    } else {
      flushList(); paragraph.push(line);
    }
  }
  flushParagraph(); flushList();
  return <div className="chat-markdown">{blocks}</div>;
}

function Conversation({
  runStatus,
  state,
  value,
  setValue,
  send,
  busy,
  loading,
  tripId,
  pendingMessage,
  choose,
  back,
  pay,
  navigate,
  download,
  openPanel,
  chat,
  chatError,
  retryChat,
}) {
  const latest = useRef(null);
  const thinking = useRef(null);
  const scroll = useRef(null);
  const composer = useRef(null);
  const messages = state?.messages || [];
  const lastAssistant = messages.findLastIndex(
    (message) => message.role === "assistant",
  );
  const lastPresentation = messages.findLastIndex((message) => message.presentation);
  const hasConversation = messages.length > 0 || pendingMessage || busy;
  const visiblePending = pendingText(messages, pendingMessage);
  const unavailable = tripId && !state && !busy && !loading;
  useEffect(() => {
    const target = busy ? thinking.current : latest.current;
    const container = scroll.current;
    if (hasConversation && target && container) {
      container.scrollTo({
        top:
          container.scrollTop +
          target.getBoundingClientRect().top -
          container.getBoundingClientRect().top -
          24,
        behavior: "instant",
      });
    }
  }, [messages.length, busy, tripId]);
  const prompt = (text) => {
    setValue(text);
    composer.current?.querySelector("textarea")?.focus();
  };
  const recommendations = !chat && state && (
    <Planner
      state={state}
      tripId={tripId}
      busy={busy}
      choose={choose}
      back={back}
      pay={pay}
      navigate={navigate}
      download={download}
    />
  );
  return (
    <div className="conversation-shell">
      <div className="conversation-scroll" ref={scroll}>
        <div
          className={`conversation-content ${hasConversation ? "has-conversation" : ""}`}
        >
          {!hasConversation && !loading && !unavailable && !chat && (
            <section className="conversation-intro">
              <span className="intro-eyebrow">
                <span /> О!ДИН ЗАПРОС — ЦЕЛАЯ ПОЕЗДКА
              </span>
              <h1>
                Ваш отпуск начинается
                <br />с <span>«хочу».</span>
                <Sparkles size={31} />
              </h1>
              <p>
                Расскажите, как хотите отдохнуть. Ваш агент соберёт
                <br className="desktop-break" /> билеты, отель и впечатления в
                одном разговоре.
              </p>
              <DestinationExplorer onSelect={prompt} />
              <div className="starter-prompts">
                {inspiration.map((item) => (
                  <button key={item.image} onClick={() => prompt(item.text)}>
                    <Icon of={item.icon} size={16} />
                    <span>{item.title}</span>
                    <ArrowUpRight size={14} />
                  </button>
                ))}
              </div>
            </section>
          )}
          {chat && !hasConversation && !loading && !chatError && <section className="chat-welcome">
            <span className="empty-icon"><Icon of={chat.kind === "support" ? LifeBuoy : chat.kind === "places" ? MapPin : MessageCircle} size={28} /></span>
            <h2>{chat.title}</h2><p>Обсудим детали вашей поездки в отдельном разговоре.</p>
            <span className="small muted">План, билеты и отель остаются в чате «План поездки».</span>
          </section>}
          {chatError && <div className="empty-state" role="alert"><h3>Не удалось открыть чат</h3><p>{chatError}</p><button className="secondary" onClick={retryChat}>Повторить загрузку</button></div>}
          {unavailable && (
            <div className="empty-state">
              <Luggage size={30} />
              <h3>Не удалось открыть поездку</h3>
              <p>Вернитесь к сохранённым планам или начните новый разговор.</p>
              <a className="primary" href="#trips">
                К моим поездкам
              </a>
            </div>
          )}
          {loading ? (
            <div className="page-loading">
              <LoaderCircle className="spin" />
              Открываем ваш разговор…
            </div>
          ) : (
            <>
              {hasConversation && (
                <div className="conversation-start">
                  <span>{chat ? chat.title : "ОДИН РАЗГОВОР. ВАША ПОЕЗДКА ЦЕЛИКОМ."}</span>
                </div>
              )}
              {messages.map((message, index) => (
                <div
                  className={`conversation-message ${message.role}`}
                  key={index}
                  ref={index === lastAssistant ? latest : null}
                >
                  {message.role === "assistant" && (
                    <span className="agent-mark">О!</span>
                  )}
                  <div className="conversation-message-body">
                    {message.role === "assistant" && (
                      <div className="agent-label">
                        О! рядом <span>ваш агент путешествий</span>
                      </div>
                    )}
                    {!chat && message.presentation && message.presentation.stage === "scenarios" && message.presentation.choices?.length && !offerItems(message.presentation, "stays").length && !offerItems(message.presentation, "transport").length ? (
                      index === lastPresentation && !busy && message.presentation.revision === state.revision ? recommendations : (
                        <fieldset className="past-recommendations" disabled>
                          <Planner state={message.presentation} tripId={tripId} busy
                            choose={() => {}} back={() => {}} pay={() => {}}
                            navigate={navigate} download={download} />
                        </fieldset>
                      )
                    ) : (
                      <>
                      <ChatText text={message.role === "user" && message.text.startsWith("/select ")
                        ? "Выбираю этот вариант" : message.text} />
                      {!chat && message.presentation && <PresentationLinks state={index === lastPresentation ? state : message.presentation} openPanel={openPanel} past={index !== lastPresentation} />}
                      </>
                    )}
                  </div>
                </div>
              ))}
              {visiblePending && (
                <div className="conversation-message user">
                  <div className="conversation-message-body">
                    <ChatText text={visiblePending} />
                  </div>
                </div>
              )}
              <div ref={thinking} className="latest-response">
                {busy && (
                  <div className="conversation-message assistant">
                    <span className="agent-mark">О!</span>
                    <div className="conversation-message-body">
                      <div className="agent-label">
                        О! рядом <span>забочусь о деталях</span>
                      </div>
                      <div className="agent-thinking">
                        <LoaderCircle size={16} className="spin" />
                        <span role="status" aria-live="polite">
                          {runStatus?.status === "running"
                            ? runStatus.label
                            : chat ? "Готовлю ответ…" : "Собираю вашу поездку…"}
                        </span>
                      </div>
                      <p className="thinking-note">
                        {chat ? "Учитываю детали поездки и историю этого разговора." : "Сравниваю источники и проверяю варианты. Это может занять несколько минут."}
                      </p>
                      {!chat && <SearchPreviews previews={runStatus?.previews} />}
                    </div>
                  </div>
                )}
                {!chat && !busy &&
                  lastAssistant < 0 &&
                  hasConversation &&
                  (state?.choices?.length && state.stage === "scenarios" ? recommendations : <PresentationLinks state={state} openPanel={openPanel} />)}
              </div>
              {state && !chat && !busy && hasConversation && (
                <div className="conversation-suggestions">
                  {[
                    "Хочу отель поближе к морю",
                    "Найди вариант подешевле",
                    "Больше времени на отдых",
                  ].map((text) => (
                    <button key={text} onClick={() => prompt(text)}>
                      {text}
                      <Plus size={12} />
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
      <div className="conversation-composer" ref={composer}>
        <div className="composer-inner">
          <Composer
            value={value}
            setValue={setValue}
            send={send}
            busy={busy || loading || !!unavailable || !!chatError}
            compact={!!hasConversation}
            contextual={!!chat}
          />
          <div className="composer-footnote">
            <span>
              <LockKeyhole size={11} /> {chat ? "Отдельный чат · контекст вашей поездки" : "Всё выбранное сохраняется в вашей поездке"}
            </span>
            <span>Бронирование и оплата — имитация</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function OfferName({ item, children }) {
  const href = safeUrl(item?.url || item?.source?.source_url);
  return href ? <a className="offer-name" href={href} target="_blank" rel="noopener noreferrer">{children || item.name}<ExternalLink size={12} aria-label="Открыть у поставщика" /></a> : children || item?.name;
}

function PresentationLinks({ state, openPanel, past = false }) {
  if (!state || !openPanel) return null;
  const links = [[Luggage, "Туры под ключ", "tours", state.options?.length], [Plane, "Билеты", "transport", offerItems(state, "transport").length], [Building2, "Отели", "stays", offerItems(state, "stays").length], [Route, "Программа", "itinerary", tripParts(state).days.length]].filter((row) => row[3]);
  if (!links.length) return null;
  return <div className="presentation-links" aria-label="Варианты поездки">
    {past && <span className="small muted">Подбор из этого ответа. Открыть актуальные варианты:</span>}
    {links.map(([Component, label, kind, count]) => <button key={kind} onClick={() => openPanel(kind)}><Component size={16} /><span>{label}{!past && <small>{kind === "itinerary" ? counted(count, "день", "дня", "дней") : counted(count, "вариант", "варианта", "вариантов")}</small>}</span><PanelRightOpen size={15} /></button>)}
    {!past && state.selected && <button onClick={() => openPanel("budget")}><Wallet size={16} /><span>Проверить поездку<small>Стоимость и оформление</small></span><ArrowRight size={15} /></button>}
  </div>;
}

function TripOptions({ kind, state, busy, choose, close, closing, changeKind, discuss, pay, tripId, navigate }) {
  const [compareIds, setCompareIds] = useState([]);
  const [comparing, setComparing] = useState(false);
  const [compact, setCompact] = useState(() => window.matchMedia("(max-width: 1000px)").matches);
  const [details, setDetails] = useState(null);
  const heading = useRef(null);
  const title = { tours: "Туры под ключ", transport: "Билеты", stays: "Отели", itinerary: "Программа по дням", budget: "Бюджет" }[kind];
  const items = offerItems(state, kind);
  const signature = items.map((item) => item.id).join("|");
  useEffect(() => {
    setCompareIds(items.slice(0, 2).map((item) => item.id));
    setComparing(false);
    setDetails(null);
  }, [kind, signature, tripId]);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 1000px)");
    const update = () => setCompact(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (!compact) heading.current?.focus({ preventScroll: true });
    const escape = (event) => { if (event.key === "Escape" && !document.querySelector("dialog[open]")) close(); };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [compact, kind]);
  const parts = tripParts(state);
  const selectedItems = items.filter((item) => compareIds.includes(item.id));
  const selection = (item) => {
    const id = offerChoice(state, item, kind);
    const selected = offerSelected(state, item, kind);
    const option = state.options?.find((row) => row.id === id);
    const other = option?.[kind === "stays" ? "transport" : "stay"];
    return <div className="panel-choice-action">
      {other && !selected && <small>В составе варианта: {other.name} · билеты + отель {money(option.budget?.known_subtotal)}</small>}
      <button className={selected ? "secondary" : "primary"} disabled={busy || selected} onClick={() => id ? choose(id) : discuss(`Хочу выбрать ${kind === "stays" ? "отель" : "билеты"}: ${item.name}. Проверь условия и обнови план.`)}>
        {selected ? <Check size={15} /> : id ? <Plus size={15} /> : <MessageCircle size={15} />}{selected ? "Выбрано" : id ? "Выбрать вариант" : "Обсудить выбор"}
      </button>
    </div>;
  };
  const content = <>
    <div className="options-tabs" aria-label="Разделы вариантов">
      {[[Luggage, "Туры", "tours"], [Plane, "Билеты", "transport"], [Building2, "Отели", "stays"], [Route, "Программа", "itinerary"], [Wallet, "Бюджет", "budget"]].map(([Component, label, key]) => <button key={key} aria-pressed={kind === key} onClick={() => changeKind(key)}><Component size={15} />{label}</button>)}
    </div>
    <div className="options-panel-scroll" key={kind}>
      {!state ? <div className="panel-empty"><LoaderCircle className="spin" />Загружаем поездку…</div> : kind === "tours" ? <section className="panel-tours" aria-label="Готовые туры">
        <p className="small muted">Дорога туда и обратно, проживание и предложенная программа — в одном варианте.</p>
        {state.options?.map((option, index) => <PackageCard key={option.id} option={option} index={index} state={state} choose={choose} busy={busy} />)}
        {!state.options?.length && <p>Расскажите о поездке — здесь появятся готовые туры.</p>}
        {canCheckout(state) && <button className="primary" disabled={busy} onClick={pay}><CreditCard size={16} />К имитации оплаты</button>}
      </section> : ["transport", "stays"].includes(kind) ? <>
        <div className="options-toolbar"><span>{counted(items.length, "вариант", "варианта", "вариантов")}{busy && " · обновляем подбор"}</span><button className="text-button" disabled={selectedItems.length < 2} aria-pressed={comparing} onClick={() => setComparing(!comparing)}>{comparing ? <List size={15} /> : <Columns2 size={15} />}{comparing ? "Карточки" : `Сравнить · ${selectedItems.length}`}</button></div>
        {comparing ? <div className="offer-comparison" style={{ "--columns": selectedItems.length }} role="group" aria-label="Сравнение вариантов">
          {selectedItems.map((item) => <div className="comparison-heading" key={item.id}><h3><OfferName item={item} /></h3>{offerSelected(state, item, kind) && <span className="panel-selected"><Check size={12} />Выбрано</span>}</div>)}
          {[['Стоимость', (item) => <><strong>{money(item.price?.amount, item.price?.currency)}</strong><small>{basis(item.price?.basis)}</small></>], ['Даты', (item) => `${date(item.start)} — ${date(item.end)}`], [kind === 'stays' ? 'Расположение' : 'Маршрут', (item) => kind === 'stays' ? item.area || 'Не указано' : `${item.origin || state.constraints?.origin || '—'} → ${item.destination || state.constraints?.destination || '—'}`], [kind === 'stays' ? 'Условия' : 'В пути', (item) => kind === 'stays' ? item.meal || item.description || 'Уточните у поставщика' : <TransportRoutes candidate={item} constraints={state.constraints} />], ['Наличие', (item) => item.source?.evidence === 'live' ? 'Найдено при поиске; перед оформлением проверим повторно' : 'Не подтверждено']].flatMap(([label, render]) => selectedItems.map((item) => <div className="comparison-cell" key={label + item.id}><small>{label}</small><div>{render(item)}</div></div>))}
          {selectedItems.map((item) => <div className="comparison-cell" key={"choose" + item.id}>{selection(item)}</div>)}
        </div> : items.map((item) => <article key={item.id} className={`panel-offer ${offerSelected(state, item, kind) ? "is-selected" : ""}`}>
          <div className="panel-offer-top">{offerSelected(state, item, kind) ? <span className="panel-selected"><Check size={13} />В вашей поездке</span> : <span className="small muted">Вариант</span>}<label className="compare-check"><input type="checkbox" aria-label={`Сравнить вариант ${item.name}`} checked={compareIds.includes(item.id)} disabled={!compareIds.includes(item.id) && compareIds.length >= 3} onChange={(event) => setCompareIds(event.target.checked ? [...compareIds, item.id] : compareIds.filter((id) => id !== item.id))} />Сравнить</label></div>
          <h3><OfferName item={item} /></h3><p className="small muted">{kind === "stays" ? item.area : `${item.origin || state.constraints?.origin || ''} → ${item.destination || state.constraints?.destination || ''}`}</p>
          <p className="small muted">{date(item.start)} — {date(item.end)}</p>
          <div className="panel-price"><strong>{money(item.price?.amount, item.price?.currency)}</strong><span>{basis(item.price?.basis)}</span></div>
          {selection(item)}
          <div className="panel-offer-links"><button className="text-button" aria-expanded={details === item.id} onClick={() => setDetails(details === item.id ? null : item.id)}>Детали<ChevronDown size={14} /></button><button className="text-button" onClick={() => discuss(`Расскажи подробнее о варианте «${item.name}».`)}><MessageCircle size={14} />Обсудить</button></div>
          {details === item.id && <div className="panel-offer-details">{item.description && <p>{item.description}</p>}{kind === "stays" ? <HotelDetails hotel={item} /> : <TransportRoutes candidate={item} constraints={state.constraints} />}<p className="small muted">{item.source?.evidence === "live" ? "Цена найдена при поиске. Подтверждение потребуется перед оформлением." : "Наличие и стоимость требуют подтверждения у поставщика."}</p></div>}
        </article>)}
        {!items.length && <div className="panel-empty"><Icon of={kind === "stays" ? Building2 : Plane} size={28} /><h3>Вариантов пока нет</h3><p>Продолжите разговор — найденные предложения появятся здесь.</p><button className="secondary" onClick={() => discuss(kind === "stays" ? "Подбери варианты проживания для моей поездки" : "Подбери билеты для моей поездки")}>Попросить ассистента</button></div>}
      </> : kind === "itinerary" ? parts.days.length ? <DayPlan days={parts.days} /> : <div className="panel-empty"><Route size={28} /><h3>Программа ещё собирается</h3><button className="secondary" onClick={() => discuss("Составь программу моей поездки по дням")}>Обсудить программу</button></div> : <section className="panel-budget"><h3>Стоимость поездки</h3>{[["Билеты", parts.transport], ["Проживание", parts.stay]].map(([label, item]) => <div className="panel-budget-row" key={label}><span>{label}</span><div><strong>{money(item?.price?.amount, item?.price?.currency)}</strong>{item?.price && <small>{basis(item.price.basis)}</small>}</div></div>)}<div className="panel-budget-row"><span>Известная сумма</span><strong>{money(parts.total)}</strong></div><p className="small muted">Неизвестные расходы не включены. Питание, активности и местные переезды могут оплачиваться отдельно.</p>{state.stage === "booked" ? <span className="panel-selected"><Check size={15} />Имитация бронирования выполнена</span> : canCheckout(state) ? <button className="primary" disabled={busy} onClick={pay}><CreditCard size={16} />К имитации оплаты</button> : <button className="secondary" disabled={busy} onClick={() => discuss("Проверь актуальность выбранных тарифов и подготовь поездку к оформлению")}>Проверить тарифы</button>}</section>}
      {state?.notice && <p className="notice">{state.notice}</p>}
      {kind === "itinerary" && state?.stage === "itinerary" && state.choices?.map((choice) => <button className="primary panel-approve" key={choice.id} disabled={busy} onClick={() => choose(choice.id)}>Мне подходит, собери поездку<ArrowRight size={15} /></button>)}
    </div>
    <div className="options-panel-footer"><button className="text-button" onClick={() => navigate("trip", tripId)}><Luggage size={15} />Вся поездка<ArrowUpRight size={14} /></button></div>
  </>;
  return compact ? <Modal title={title} close={close} className={`options-sheet ${closing ? "is-closing" : ""}`}><section id="trip-options-panel">{content}</section></Modal> : <aside className={`trip-options-panel ${closing ? "is-closing" : ""}`} id="trip-options-panel" aria-label="Варианты поездки"><div className="options-panel-head"><div><span className="eyebrow">ВАША ПОЕЗДКА</span><h2 ref={heading} tabIndex={-1}>{title}</h2></div><button className="icon-button" onClick={close} aria-label="Закрыть панель вариантов"><X size={19} /></button></div>{content}</aside>;
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

function HotelDetails({ hotel }) {
  const [failed, setFailed] = useState([]);
  const photos = [...new Set(hotel?.photos || [])]
    .map(safeUrl).filter((url) => url?.startsWith("https:") && !failed.includes(url));
  return (
    <>
      {photos.length > 0 && (
        <div className="hotel-photos" aria-label={`Фотографии отеля ${hotel?.name || ""}`}>
          {photos.map((url, index) => (
            <a key={url} href={url} target="_blank" rel="noreferrer">
              <img src={url} alt={`${hotel?.name || "Отель"} — фото ${index + 1}`}
                loading="lazy" referrerPolicy="no-referrer"
                onError={() => setFailed((previous) => [...previous, url])} />
            </a>
          ))}
        </div>
      )}
      {hotel?.amenities?.length > 0 && (
        <div className="hotel-amenities">
          <strong>Услуги отеля</strong>
          <div className="tags">{hotel.amenities.map((amenity) => <span key={amenity}>{amenity}</span>)}</div>
        </div>
      )}
    </>
  );
}

function TransportRoutes({ candidate, constraints = {} }) {
  return (
    <div className="transport-routes">
      {transportRoutes(candidate).map((leg, index) => (
        <section className="transport-leg" key={index} aria-label={index === 0 ? "Билет туда" : "Билет обратно"}>
          <div className="transport-leg-heading">
            <strong>{index === 0 ? "Туда" : "Обратно"}</strong>
            <span>{[...(leg.carriers || []), ...(leg.flight_numbers || [])].join(" · ")}</span>
          </div>
          <div className="flight-route">
            <div>
              <strong>{time(leg.departure_at)}</strong>
              <span>{leg.origin || (index === 0 ? constraints.origin : constraints.destination) || "Отправление"}</span>
              <small>{date(leg.departure_at || leg.start)}</small>
            </div>
            <div className="flight-line">
              <span>{leg.duration_minutes
                ? `${Math.floor(leg.duration_minutes / 60)} ч ${leg.duration_minutes % 60} мин`
                : "Время в пути уточняется"}</span>
              <i />
              <small>{leg.transfers === 0 ? "Прямой" : leg.transfers == null
                ? "Пересадки уточняются" : `${leg.transfers} пересадок`}</small>
            </div>
            <div>
              <strong>{time(leg.arrival_at)}</strong>
              <span>{leg.destination || (index === 0 ? constraints.destination : constraints.origin) || "Прибытие"}</span>
              <small>{leg.arrival_at ? date(leg.arrival_at) : "Прибытие уточняется"}</small>
            </div>
          </div>
        </section>
      ))}
    </div>
  );
}

function SearchPreviews({ previews }) {
  const roles = {
    transport: "Билеты",
    stays: "Проживание",
    experience: "Места и программа",
  };
  return (
    Object.keys(previews || {}).length > 0 && (
      <div
        className="search-previews"
        aria-label="Предварительные результаты поиска"
      >
        {Object.entries(previews).map(([role, cards]) => (
          <div key={role}>
            <strong>
              <CheckCircle2 size={14} /> {roles[role]}
            </strong>
            {cards.map((card) => (
              <span key={card.id}>{card.title}</span>
            ))}
          </div>
        ))}
        <p>Предварительные результаты. Агент ещё проверяет совместимость.</p>
      </div>
    )
  );
}

function PackageCard({ option, index, state, choose, busy }) {
  const selected = state.selected === option.id;
  const people = state.constraints?.adults;
  return (
    <article className={`package-card ${selected ? "is-selected" : ""}`}>
      <div className="package-heading">
        <span className="choice-kicker">ВАРИАНТ {index + 1}</span>
        {selected && (
          <span className="package-selected">
            <Check size={14} /> Выбран
          </span>
        )}
      </div>
      <h3><OfferName item={option.stay} /></h3>
      <p className="package-area">
        <MapPin size={14} />
        {option.stay?.area || "Россия"}
      </p>
      <div className="package-components">
        <div>
          <Icon
            of={
              option.transport?.transport_mode === "rail" ? TrainFront : Plane
            }
            size={18}
          />
          <span>
            <strong><OfferName item={option.transport} /></strong>
            <small>
              {date(option.transport?.start)} — {date(option.transport?.end)} ·
              туда и обратно
            </small>
          </span>
        </div>
        <div>
          <Building2 size={18} />
          <span>
            <strong>Проживание</strong>
            <small>
              {date(option.stay?.start)} — {date(option.stay?.end)}
            </small>
          </span>
        </div>
      </div>
      <div className="package-price">
        <strong>{money(option.budget?.known_subtotal)}</strong>
        <span>билеты + отель за всех</span>
        {people > 0 && (
          <small>
            {money(Number(option.budget?.known_subtotal) / people)} на человека
          </small>
        )}
      </div>
      {option.days?.some((day) => day.candidates?.length) && <p className="package-program"><Route size={16} /><span>{[...new Set(option.days.flatMap((day) => day.candidates || []).map((item) => item.name))].slice(0, 3).join(" · ")}</span></p>}
      <details className="package-details">
        <summary>
          Программа и условия <ChevronDown size={14} />
        </summary>
        <DayPlan days={option.days || []} />
        <HotelDetails hotel={option.stay} />
        {option.transport && <TransportRoutes candidate={option.transport} constraints={state.constraints} />}
        <SourceLink url={option.transport?.url}>Билеты у поставщика</SourceLink>
        <SourceLink url={option.stay?.url}>Отель у поставщика</SourceLink>
      </details>
      <button
        className={selected ? "secondary" : "primary"}
        disabled={busy || selected}
        onClick={() => choose(option.id)}
      >
        {selected ? "Этот вариант выбран" : `Выбрать вариант ${index + 1}`}
        <Check size={16} />
      </button>
    </article>
  );
}

function AutonomousPlan({
  state,
  tripId,
  busy,
  choose,
  pay,
  navigate,
  download,
}) {
  const staysOnly = state.focus === "stays";
  const componentOnly = staysOnly || state.focus === "transport";
  const options = state.options || [];
  const candidates = Object.values(state.results || {}).flatMap(
    (result) => result.candidates || [],
  );
  if (state.stage === "scenarios" && state.choices?.length)
    return <section className="agent-recommendations"><h2>Выберите направление</h2><div className="choices-grid scenarios-grid">
      {state.choices.map((choice, index) => <ChoiceCard key={choice.id} choice={choice} index={index} state={state} choose={choose} busy={busy} />)}
    </div></section>;
  if (state.stage === "booked")
    return (
      <Summary
        state={state}
        tripId={tripId}
        pay={pay}
        navigate={navigate}
        download={download}
        expanded
      />
    );
  return (
    <section className="agent-recommendations" aria-label="Предложения агента">
      {(options.length > 0 || state.cards?.length > 0) && (
        <div className="recommendation-heading">
          <h2>
            {staysOnly ? "Проживание под ваш запрос" : componentOnly ? "Варианты проезда" : "Варианты вашей поездки"}
          </h2>
          <span>{tripStatus(state)}</span>
        </div>
      )}
      {componentOnly || (!options.length && state.cards?.length > 0) ? (
        <>
          <div className="choices-grid offers-grid">
            {state.choices?.map((choice, index) => (
              <ChoiceCard
                key={choice.id}
                choice={choice}
                index={index}
                state={{ ...state, stage: state.cards?.find((card) => card.id === choice.id)?.kind || state.focus }}
                choose={choose}
                busy={busy || state.selected_stay === choice.id}
              />
            ))}
          </div>
          {staysOnly && state.selected_stay && (
            <p className="notice">
              Отель выбран. Попросите агента добавить билеты и программу, чтобы
              собрать поездку.
            </p>
          )}
        </>
      ) : options.length > 0 ? (
        <>
          <div className="packages-grid">
            {options.map((option, index) => (
              <PackageCard
                key={option.id}
                option={option}
                index={index}
                state={state}
                choose={choose}
                busy={busy}
              />
            ))}
          </div>
          {state.selected && (
            <Summary
              state={state}
              tripId={tripId}
              pay={pay}
              navigate={navigate}
              download={download}
            />
          )}
        </>
      ) : candidates.length > 0 ? (
        <div className="partial-results">
          <h3>Уже нашлось для вашей поездки</h3>
          <p className="small muted">
            Готового пакета пока нет. Сохранили найденное для продолжения
            поиска.
          </p>
          {candidates.slice(0, 6).map((item) => (
            <div className="partial-offer" key={item.id}>
              <Icon
                of={
                  item.role === "stays"
                    ? Building2
                    : item.role === "transport"
                      ? item.transport_mode === "rail"
                        ? TrainFront
                        : Plane
                      : MapPin
                }
                size={18}
              />
              <div>
                <strong><OfferName item={item} /></strong>
                <p>
                  {money(item.price?.amount, item.price?.currency)}
                  {item.price && ` · ${basis(item.price.basis)}`}
                </p>
                <SourceLink url={item.url || item.source?.source_url} />
                {item.role === "stays" && <HotelDetails hotel={item} />}
                {item.role === "transport" && <TransportRoutes candidate={item} constraints={state.constraints} />}
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
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
    required_baggage_unverified: "Требуемый багаж не подтверждён",
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
          <div className="destination-banner">
            <MapPin size={30} />
            <span>{scenario?.destination || "Россия"}</span>
            <small>Идея поездки · цены и наличие ещё не проверены</small>
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
              Стоимость уточним при подборе билетов и отеля
            </span>
          </div>
        </>
      ) : (
        <div className="choice-content">
          <div className="choice-top">
            <span className="provider-icon">
              <Icon
                of={
                  stage === "transport"
                    ? candidate?.transport_mode === "avia"
                      ? Plane
                      : Route
                    : Building2
                }
              />
            </span>
            <div>
              <span className="choice-kicker">
                {stage === "transport"
                  ? "ТУДА И ОБРАТНО"
                  : candidate?.area || "ПРОЖИВАНИЕ"}
              </span>
              <h3><OfferName item={{ ...candidate, url: card?.url || candidate?.url }} >{choice.title}</OfferName></h3>
            </div>
            {index === 0 && <span className="soft-badge">Вариант 1</span>}
          </div>
          {stage === "transport" && <TransportRoutes candidate={{ ...dates, ...candidate }} constraints={state.constraints} />}
          {stage === "stays" && (
            <div className="stay-dates">
              <CalendarDays size={17} />
              {date(dates.start)} — {date(dates.end)}
              <span>
                <Users size={16} />
                {party(
                  candidate?.adults ?? state.constraints?.adults,
                  candidate?.children_ages ?? state.constraints?.children_ages,
                )}
              </span>
            </div>
          )}
          {stage === "stays" && <HotelDetails hotel={candidate} />}
          <p>{candidate?.description || card?.description || choice.details}</p>
          <div className="tags">
            {warnings.map((w) => (
              <span className="warning-tag" key={w}>
                {warningLabels[w] || w}
              </span>
            ))}
          </div>
          <div className="choice-footer">
            <div>
              <strong className="price">
                {money(price?.amount, price?.currency)}
              </strong>
              <span className="small muted">
                {basis(price?.basis)} · {price?.currency || "RUB"}
              </span>
            </div>
            <button
              className="primary"
              disabled={busy || card?.selectable === false || card?.freshness === "expired"}
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
  const receipt = state.stage === "booked" ? state.receipt : null;
  const option = currentOption(state);
  const c = {
    ...state.constraints,
    start: option?.transport?.start || state.constraints?.start,
    end: option?.transport?.end || state.constraints?.end,
  };
  const parts = tripParts(state);
  const items =
    receipt?.items ||
    [parts.transport, parts.stay]
      .filter(Boolean)
      .map((i) => ({ ...i, kind: i.role }));
  const days = parts.days;
  const total = parts.total;
  const componentCost = (item) =>
    item?.price?.amount == null ||
    (item.price.currency && item.price.currency !== "RUB") ||
    !["party", "room_stay", "person", "ticket"].includes(item.price.basis)
      ? 0
      : Number(item.price.amount) *
        (["person", "ticket"].includes(item.price.basis)
          ? (c.adults || 0) + (c.children_ages?.length || 0) || 1
          : 1);
  const transportCost = componentCost(
    items.find((i) => i.kind === "transport"),
  );
  const stayCost = componentCost(items.find((i) => i.kind === "stays"));
  const costSum = transportCost + stayCost;
  if (state.autonomous && !option && !receipt)
    return (
      <div className="empty-state">
        <Luggage size={30} />
        <h3>
          {state.focus === "stays"
            ? "Подбираем проживание"
            : "Поездка ещё собирается"}
        </h3>
        <p>
          Продолжите разговор с агентом. Готовые варианты появятся здесь после
          поиска и проверки.
        </p>
        <button className="primary" onClick={() => navigate("plan", tripId)}>
          Обсудить поездку
        </button>
      </div>
    );
  return (
    <div className="trip-summary">
      <div className={`summary-banner ${receipt ? "booked" : ""}`}>
        <span>
          <Icon of={receipt ? CheckCircle2 : Luggage} size={26} />
        </span>
        <div>
          <span className="eyebrow">
            {receipt
              ? "МОЖНО ПРЕДВКУШАТЬ"
              : state.autonomous && !state.selected
                ? "ПРЕДПРОСМОТР ВАРИАНТА"
                : "ПАЗЛ СЛОЖИЛСЯ"}
          </span>
          <h2>{receipt ? "Ваше путешествие ждёт" : "Ваша поездка, целиком"}</h2>
          <p>
            {date(c.start)} — {date(c.end)} · {party(c.adults, c.children_ages)}{" "}
            · {c.origin || "Город уточняется"}
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
      <TripMap state={state} />
      <div className="summary-items">
        {items.map((item, i) => (
          <details className="summary-component" key={i}>
            <summary>
              <span className="component-icon">
                <Icon
                  of={
                    item.kind === "transport"
                      ? (item.transport_mode ||
                          item.details?.transport_mode) === "rail"
                        ? TrainFront
                        : Plane
                      : Building2
                  }
                />
              </span>
              <div>
                <small>
                  {item.kind === "transport"
                    ? "Билеты туда и обратно"
                    : "Ваш отель"}
                </small>
                <strong><OfferName item={{ ...item.details, ...item }} /></strong>
              </div>
              <ChevronDown size={18} />
            </summary>
            <div className="component-details">
              {item.kind === "transport" ? (
                <TransportRoutes candidate={{ ...item.details, ...item }} constraints={state.constraints} />
              ) : <HotelDetails hotel={{ ...item.details, ...item }} />}
              <p>
                {item.description ||
                  item.details?.description ||
                  "Подробности уточняйте у поставщика."}
              </p>
              <p>
                {money(item.price?.amount, item.price?.currency)} ·{" "}
                {basis(item.price?.basis)}
              </p>
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
          canCheckout(state) && (
            <button className="primary" onClick={pay}>
              <CreditCard size={17} />
              Забронировать поездку
            </button>
          )
        )}
      </div>
      {!receipt && state.selected && !canCheckout(state) && (
        <p className="small muted">
          Перед оформлением попросите агента обновить тарифы поездки.
        </p>
      )}
      {expanded && (
        <>
          <details className="itinerary-details">
            <summary>
              <Route size={17} />
              Программа по дням<span>{counted(days.length, "день", "дня", "дней")}</span>
              <ChevronDown size={16} />
            </summary>
            <DayPlan days={days} />
          </details>
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
                          <OfferName item={{ ...item.details, ...item }} /> · {item.details?.start} —{" "}
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
  if (state.autonomous)
    return (
      <AutonomousPlan
        state={state}
        tripId={tripId}
        busy={busy}
        choose={choose}
        pay={pay}
        navigate={navigate}
        download={download}
      />
    );
  const stage = state.stage || "scenarios";
  const index = stages.indexOf(stage);
  const titles = {
    scenarios: "Какой отдых вам ближе?",
    transport: "Как доберёмся",
    stays: "Ваше место у моря. Или в горах.",
    itinerary: "Дни, которые запомнятся",
    review: "Ваша поездка сложилась",
    booked: "Всё важное — с вами",
  };
  const c = state.constraints || {};
  const parts = tripParts(state);
  return (
    <section className="agent-recommendations" aria-label="Предложения агента">
      {index < 4 && (
        <div className="recommendation-heading">
          <h2>{titles[stage]}</h2>
          <span>{stage === "booked" ? "Сохранено" : "Под ваш запрос"}</span>
        </div>
      )}
      {c.start && index < 4 && (
        <div className="trip-pills">
          <span>
            <CalendarDays size={13} />
            {date(c.start)} — {date(c.end)}
          </span>
          <span>
            <Users size={13} />
            {party(c.adults, c.children_ages)}
          </span>
          {c.budget && (
            <span>
              <Wallet size={13} />
              до {money(c.budget)}{" "}
              {c.budget_basis === "person" ? "/ чел." : "на всех"}
            </span>
          )}
        </div>
      )}
      {state.pending_check_in && (
        <div className="notice warning">
          <CalendarDays size={18} />
          <span>
            Прибытие {date(state.pending_check_in)}. Обсудите с агентом новую
            дату заселения и подтвердите её в чате.
          </span>
        </div>
      )}
      {state.notice && (
        <div className="notice">
          <LifeBuoy size={18} />
          <span>{state.notice}</span>
        </div>
      )}
      {index < 3 ? (
        <div
          className={`choices-grid ${stage === "scenarios" ? "scenarios-grid" : "offers-grid"}`}
        >
          {state.choices?.map((choice, i) => (
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
      ) : stage === "itinerary" ? (
        <>
          <TripMap state={state} />
          <details className="itinerary-details">
            <summary>
              <Route size={17} />
              Программа по дням<span>{counted(parts.days.length, "день", "дня", "дней")}</span>
              <ChevronDown size={16} />
            </summary>
            <DayPlan days={parts.days} />
          </details>
          {state.choices?.map((choice) => (
            <button
              key={choice.id}
              className="primary approve-program"
              disabled={busy}
              onClick={() => choose(choice.id)}
            >
              Мне подходит, собери поездку
              <ArrowRight size={17} />
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
      {index < 4 && !state.choices?.length && (
        <div className="agent-empty">
          <MessageCircle size={17} />
          <span>
            {state.status === "error"
              ? "Поиск не завершился. Напишите агенту, чтобы попробовать ещё раз."
              : "Продолжим в разговоре — уточните пожелания, и я подберу варианты."}
          </span>
        </div>
      )}
      {index > 0 && stage !== "booked" && (
        <details className="edit-trip">
          <summary>
            <SlidersHorizontal size={14} />
            Изменить выбранное
          </summary>
          <p>При новом выборе связанные предложения будут подобраны заново.</p>
          <div>
            {stages
              .slice(0, index)
              .filter((item) => item !== "review")
              .map((item) => (
                <button
                  className="secondary"
                  key={item}
                  disabled={busy}
                  onClick={() => back(item)}
                >
                  {
                    {
                      scenarios: "Идея поездки",
                      transport: "Билеты",
                      stays: "Отель",
                      itinerary: "Программа",
                    }[item]
                  }
                </button>
              ))}
          </div>
        </details>
      )}
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

function Trips({ account, auth, trips, navigate, reload, run, removeTrip, busy }) {
  const [filter, setFilter] = useState("all");
  const [removing, setRemoving] = useState(null);
  const [deleting, setDeleting] = useState(false);
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
            <article
              className="history-card"
              key={t.trip_id}
            >
              <button className="history-open-button"
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
                  {t.state.autonomous
                    ? tripStatus(t.state)
                    : stageNames[stages.indexOf(t.state.stage || "scenarios")]}
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
                      ? party(t.state.constraints.adults, t.state.constraints.children_ages)
                      : "Детали уточняются"}
                  </span>
                  <span className="history-open">
                    <ArrowUpRight size={20} />
                  </span>
                </div>
              </div>
              </button>
              <div className="history-actions">
                <button className="text-button danger" disabled={busy || deleting}
                  aria-label={`Удалить поездку: ${t.state.constraints?.destination || "Новая история"}`}
                  onClick={() => setRemoving(t)}>
                  <Trash2 size={16} /> Удалить поездку
                </button>
              </div>
            </article>
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
      {removing && (
        <Modal title="Удалить поездку?" close={() => { if (!deleting) setRemoving(null); }}>
          <p>Поездка «{removing.state.constraints?.destination || "Новая история"}» и переписка с агентом будут удалены.</p>
          <div className="modal-actions">
            <button className="secondary" disabled={deleting} onClick={() => setRemoving(null)}>Отмена</button>
            <button className="primary danger-button" disabled={deleting} onClick={async () => {
              setDeleting(true);
              const removed = await run(() => removeTrip(removing.trip_id));
              setDeleting(false);
              if (removed) setRemoving(null);
            }}>
              {deleting ? <LoaderCircle size={16} className="spin" /> : <Trash2 size={16} />}
              {deleting ? "Удаляем…" : "Удалить"}
            </button>
          </div>
        </Modal>
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
      <TripMap state={state} />
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
  const [drafts, setDrafts] = useState({});
  const [runningTrips, setRunningTrips] = useState(() => new Set());
  const [runStatus, setRunStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [payment, setPayment] = useState(false);
  const [pendingMessages, setPendingMessages] = useState({});
  const [mobileNav, setMobileNav] = useState(false);
  const [panelKind, setPanelKind] = useState(null);
  const [panelClosing, setPanelClosing] = useState(false);
  const panelCloseTimer = useRef(null);
  const [chats, setChats] = useState([]);
  const [chat, setChat] = useState(null);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState("");
  const [chatsError, setChatsError] = useState(false);
  const [chatDialog, setChatDialog] = useState(null);
  const [creatingChat, setCreatingChat] = useState(false);
  const [chatTitle, setChatTitle] = useState("");
  const [chatToDelete, setChatToDelete] = useState(null);
  const [page, tripId, chatId] = route.split("/");
  const sessionKey = tripId ? tripId + (chatId ? ":" + chatId : "") : "new";
  const pendingMessage = pendingMessages[sessionKey];
  const activeChat = chat?.chat_id === chatId ? chat : null;
  const activeChatError = chatError?.id === sessionKey ? chatError.message : "";
  const value = drafts[sessionKey] || "";
  const setValue = (next) => setDrafts((current) => ({ ...current, [sessionKey]: typeof next === "function" ? next(current[sessionKey] || "") : next }));
  const busy = runningTrips.has(sessionKey);
  const chatVersion = useRef(0);
  const panelTrigger = useRef(null);
  const panelResults = useRef("");
  const chatsVersion = useRef(0);
  useEffect(() => {
    setRunStatus(null);
    if (!busy || !tripId || chatId) return;
    const source = new EventSource(`/trips/${tripId}/events`);
    source.onmessage = (event) => {
      try {
        setRunStatus(JSON.parse(event.data));
      } catch {
        source.close();
      }
    };
    return () => source.close();
  }, [busy, tripId, chatId]);
  const operation = useRef(new Set());
  const snapshotVersion = useRef(0);
  const draftVersion = useRef(0);
  const main = useRef(null);
  const navigate = (page, id, conversationId) => {
    const next = page + (id ? "/" + id : "") + (conversationId ? "/" + conversationId : "");
    setRoute(next);
    window.location.hash = next;
    setMobileNav(false);
  };
  useEffect(() => {
    main.current?.scrollTo({ top: 0, behavior: "instant" });
  }, [route]);
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
  const reloadChats = async () => {
    if (!tripId) return;
    const id = tripId;
    const version = ++chatsVersion.current;
    try {
      const list = await api(`/trips/${id}/chats`);
      if (version === chatsVersion.current && window.location.hash.slice(1).split("/")[1] === id) { setChats(Array.isArray(list) ? list : []); setChatsError(false); }
    } catch { if (version === chatsVersion.current && window.location.hash.slice(1).split("/")[1] === id) setChatsError(true); }
  };
  useEffect(() => { setChats([]); setChatsError(false); if (account && tripId) reloadChats(); }, [tripId, account?.id]);
  const loadChat = async () => {
    if (!chatId || !account) return;
    const version = ++chatVersion.current;
    setChat(null); setChatLoading(true); setChatError("");
    try {
      const next = await api(`/trips/${tripId}/chats/${chatId}`);
      if (version === chatVersion.current) setChat(next);
    } catch (e) { if (version === chatVersion.current) setChatError({ id: sessionKey, message: e.message }); }
    finally { if (version === chatVersion.current) setChatLoading(false); }
  };
  useEffect(() => {
    setChat(null); setChatError(""); setChatLoading(false);
    loadChat();
    return () => { chatVersion.current += 1; };
  }, [chatId, tripId, account?.id]);
  useEffect(() => { clearTimeout(panelCloseTimer.current); setPanelKind(null); setPanelClosing(false); panelResults.current = ""; }, [tripId]);
  useEffect(() => () => clearTimeout(panelCloseTimer.current), []);
  useEffect(() => {
    if (!state || chatId || page !== "plan") return;
    const hotels = offerItems(state, "stays"), tickets = offerItems(state, "transport");
    const signature = JSON.stringify([tripId, state.revision, state.stage, state.options?.map((row) => row.id), hotels.map((row) => row.id), tickets.map((row) => row.id)]);
    if (signature === panelResults.current) return;
    panelResults.current = signature;
    if (window.matchMedia("(min-width: 1001px)").matches && (hotels.length || tickets.length)) setPanelKind(state.stage === "booked" ? "budget" : !state.autonomous && state.stage === "itinerary" ? "itinerary" : state.focus === "transport" ? "transport" : state.options?.length && !state.focus ? "tours" : hotels.length ? "stays" : "transport");
  }, [state, page, chatId, tripId]);
  const closePanel = () => { clearTimeout(panelCloseTimer.current); setPanelClosing(true); panelCloseTimer.current = setTimeout(() => { setPanelKind(null); setPanelClosing(false); const target = panelTrigger.current?.isConnected && !panelTrigger.current.closest("[inert]") ? panelTrigger.current : document.querySelector(".topbar-options"); target?.focus({ preventScroll: true }); }, window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 180); };
  const openPanel = (kind) => {
    if (!tripId) return;
    panelTrigger.current = document.activeElement;
    clearTimeout(panelCloseTimer.current); setPanelClosing(false);
    setPanelKind(kind);
    if (page !== "plan") navigate("plan", tripId);
    setMobileNav(false);
  };
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
    const version = ++snapshotVersion.current;
    setState(null);
    setProgress(null);
    setLoading(false);
    if (!tripId || !account) return;
    setLoading(true);
    api(`/trips/${tripId}`)
      .then((s) => {
        if (active && snapshotVersion.current === version) setState(s);
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
  async function run(fn, isCurrent) {
    const startRoute = window.location.hash;
    setError("");
    try {
      return await fn();
    } catch (e) {
      if (isCurrent ? !isCurrent() : window.location.hash !== startRoute) return null;
      setError(
        e.message || "Не удалось связаться с сервером. Проверьте соединение.",
      );
      if (e.status === 401) setAuth(true);
      const [, activeTripId, activeChatId] = window.location.hash.slice(1).split("/");
      if ([409, 504].includes(e.status) && activeTripId) {
        try {
          const activeRoute = window.location.hash;
          const current = await api(`/trips/${activeTripId}` + (activeChatId ? `/chats/${activeChatId}` : ""));
          if (window.location.hash === activeRoute) {
            if (activeChatId) { chatVersion.current += 1; setChat(current); setChatLoading(false); }
            else {
            snapshotVersion.current += 1;
            setState(current);
            }
          }
        } catch {}
      }
      return null;
    }
  }
  async function mutate(fn, operationKey = sessionKey) {
    const key = operationKey;
    if (operation.current.has(key)) return;
    const keys = new Set([key]);
    operation.current.add(key);
    setRunningTrips(new Set(operation.current));
    try {
      await run(() => fn(keys), () => { const [, id, cid] = window.location.hash.slice(1).split("/"); return keys.has(id ? id + (cid ? ":" + cid : "") : "new"); });
    } finally {
      for (const id of keys) operation.current.delete(id);
      setRunningTrips(new Set(operation.current));
    }
  }
  async function send() {
    if (!value.trim() || operation.current.has(sessionKey)) return;
    if (!account) {
      setAuth(true);
      return;
    }
    const text = value.trim();
    const draft = draftVersion.current;
    const requestId = crypto.randomUUID();
    setValue("");
    setPendingMessages((current) => ({ ...current, [sessionKey]: { tripId, chatId, text, requestId } }));
    const clearPending = () => setPendingMessages((current) => Object.fromEntries(Object.entries(current).filter(([, pending]) => pending.requestId !== requestId)));
    let sent = false;
    let targetTripId = tripId;
    await mutate(async (keys) => {
      let id = tripId;
      if (!id) {
        id = (await api("/trips", { method: "POST" })).trip_id;
        targetTripId = id;
        keys.add(id);
        operation.current.add(id);
        keys.delete("new");
        operation.current.delete("new");
        setRunningTrips(new Set(operation.current));
        if (draftVersion.current === draft && window.location.hash.slice(1) === "plan") {
          setPendingMessages((current) => ({ ...Object.fromEntries(Object.entries(current).filter(([, pending]) => pending.requestId !== requestId)), [id]: { tripId: id, text, requestId } }));
          navigate("plan", id);
        }
      }
      const current = chatId ? chat || await api(`/trips/${id}/chats/${chatId}`) : id === tripId && state ? state : await api(`/trips/${id}`);
      const startRoute = "plan/" + id + (chatId ? "/" + chatId : "");
      const next = await api(`/trips/${id}` + (chatId ? `/chats/${chatId}` : "") + "/messages", {
        method: "POST",
        body: { message: text, revision: current.revision },
      });
      sent = true;
      clearPending();
      if (window.location.hash.slice(1) === startRoute) {
        if (chatId) { chatVersion.current += 1; setChat(next); setChatLoading(false); }
        else { snapshotVersion.current += 1; setState(next); setLoading(false); }
      }
      if (!chatId) await reloadTrips();
    });
    clearPending();
    if (!sent && window.location.hash.slice(1) === "plan" + (targetTripId ? "/" + targetTripId : "") + (chatId ? "/" + chatId : "")) {
      const key = targetTripId ? targetTripId + (chatId ? ":" + chatId : "") : "new";
      setDrafts((current) => ({ ...current, [key]: current[key] || text }));
    }
  }
  const removeTrip = async (id) => {
    await api(`/trips/${id}`, { method: "DELETE" });
    setTrips((current) => current.filter((trip) => trip.trip_id !== id));
    if (tripId === id) {
      setState(null);
      setProgress(null);
      navigate("trips");
    }
    setSuccess("Поездка удалена");
    return true;
  };
  const choose = (id) => {
    if (chatId) navigate("plan", tripId);
    return mutate(async () => {
      const next = await api(
        `/trips/${tripId}/select/${encodeURIComponent(id)}?revision=${state.revision}`,
        { method: "POST" },
      );
      if (window.location.hash.slice(1).split("/")[1] === tripId) {
        snapshotVersion.current += 1;
        setState(next);
        setLoading(false);
      }
      await reloadTrips();
    }, tripId);
  };
  const back = (stage) =>
    mutate(async () => {
      const next = await api(`/trips/${tripId}/back`, {
        method: "POST",
        body: { stage, revision: state.revision },
      });
      if (window.location.hash.slice(1) === "plan/" + tripId) {
        snapshotVersion.current += 1;
        setState(next);
        setLoading(false);
      }
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
  const discussPlan = (text) => {
    setDrafts((current) => ({ ...current, [tripId]: text }));
    navigate("plan", tripId);
    if (window.matchMedia("(max-width: 1000px)").matches) closePanel();
    requestAnimationFrame(() => document.querySelector(".conversation-composer textarea")?.focus());
  };
  const createChat = async (id, kind, text = "", title = "") => {
    if (creatingChat) return;
    setCreatingChat(true);
    const originRoute = window.location.hash;
    await run(async () => {
      const target = id || (await api("/trips", { method: "POST" })).trip_id;
      const created = await api(`/trips/${target}/chats`, { method: "POST", body: { kind, title } });
      setDrafts((current) => ({ ...current, [target + ":" + created.chat_id]: text }));
      if (window.location.hash === originRoute) {
        setChatDialog(null); setChatTitle("");
        if (target === tripId) { chatsVersion.current += 1; setChats((current) => [...current, created]); }
        navigate("plan", target, created.chat_id);
      }
      await reloadTrips();
    });
    setCreatingChat(false);
  };
  const discussSupport = (text) => {
    if (!account) { setAuth(true); return; }
    if (tripId) createChat(tripId, "support", text, text.startsWith("Помоги составить письмо:") ? text.slice(0, 120) : "Помощь в пути");
    else setChatDialog({ kind: "support", text });
  };
  const logout = () =>
    run(async () => {
      await api("/api/auth/logout", { method: "POST" });
      setAccount(null);
      setState(null);
      setDrafts({});
      setPendingMessages({});
      setChats([]);
      setChat(null);
      navigate("plan");
    });
  const planning = page === "plan";
  const newTrip = () => {
    draftVersion.current += 1;
    snapshotVersion.current += 1;
    setState(null);
    setProgress(null);
    setLoading(false);
    setRunStatus(null);
    setPayment(false);
    setPendingMessages((current) => Object.fromEntries(Object.entries(current).filter(([key]) => key !== "new")));
    setError("");
    setDrafts((current) => ({ ...current, new: "" }));
    navigate("plan");
  };
  const pageTitle =
    {
      trips: "Мои поездки",
      trip: "Ваша поездка",
      track: "В пути",
      profile: "Личный кабинет",
      support: "Помощь в пути",
    }[page] || "Новая поездка";
  return (
    <div className="app-shell">
      <Sidebar
        account={account}
        state={state}
        trips={trips}
        tripId={tripId}
        page={page}
        navigate={navigate}
        newTrip={newTrip}
        auth={() => setAuth(true)}
        busy={busy}
        open={mobileNav}
        close={() => setMobileNav(false)}
        openPanel={openPanel}
        panelKind={panelKind}
        chats={chats}
        chatId={chatId}
        openChat={(id) => navigate("plan", tripId, id)}
        newChat={() => { setChatTitle(""); setChatDialog({ kind: "general", text: "" }); }}
        chatsError={chatsError}
        reloadChats={reloadChats}
        removeChat={setChatToDelete}
      />
      <div className="app-main" inert={mobileNav ? true : undefined}>
        <header className="app-topbar">
          <div className="topbar-title">
            <button
              className="sidebar-toggle icon-button"
              aria-label="Открыть меню"
              aria-expanded={mobileNav}
              onClick={() => setMobileNav(!mobileNav)}
            >
              <Menu size={21} />
            </button>
            <span>
              <strong>
                {planning && tripId
                  ? chatId ? activeChat?.title || "Чат поездки" : state?.constraints?.destination || "Ваша поездка"
                  : pageTitle}
              </strong>
              <small>
                {planning
                  ? chatId ? "Отдельный разговор в вашей поездке" : "Один запрос · один общий план"
                  : "О! рядом · ваш агент путешествий"}
              </small>
            </span>
            {planning && (
              <span className="topbar-status">
                <span />
                {chatId ? "Чат поездки" : state?.stage === "booked"
                  ? tripStatus(state)
                  : "Планируем вместе"}
              </span>
            )}
          </div>
          <div className="topbar-actions">
            {planning && tripId && (
              <button className="topbar-trip topbar-options" onClick={() => openPanel(panelKind || (state?.options?.length ? "tours" : "stays"))} aria-label="Открыть варианты поездки" aria-expanded={!!panelKind} aria-controls="trip-options-panel"><PanelRightOpen size={16} />Варианты</button>
            )}
            {planning && tripId && (
              <button
                className="topbar-trip"
                onClick={() => navigate("trip", tripId)}
              >
                <Luggage size={15} />
                Вся поездка
                <ArrowUpRight size={14} />
              </button>
            )}
            <button
              className="topbar-avatar"
              aria-label={account ? "Личный кабинет" : "Войти"}
              onClick={() => (account ? navigate("profile") : setAuth(true))}
            >
              {account?.name?.[0] || <CircleUserRound size={20} />}
            </button>
          </div>
        </header>
        <main
          ref={main}
          className={planning ? "conversation-main" : "service-main"}
        >
          {page === "login" ? (
            <div className="page-loading">
              <LoaderCircle className="spin" />
              Открываем ваши поездки…
            </div>
          ) : planning ? (
            tripId && !account && authChecked ? (
              <AccountRequired auth={() => setAuth(true)} />
            ) : (
              <div className={`planning-workspace ${panelKind ? "has-options" : ""}`}><Conversation
                key={`chat-${sessionKey}`}
                runStatus={runStatus}
                state={chatId ? { ...state, messages: activeChat?.messages || [] } : state}
                value={value}
                setValue={setValue}
                send={send}
                busy={busy}
                loading={loading || chatLoading || (!!chatId && !activeChat && !activeChatError) || (!!tripId && !authChecked)}
                tripId={tripId}
                pendingMessage={
                  pendingMessage?.tripId === tripId && pendingMessage?.chatId === chatId ? pendingMessage?.text : ""
                }
                choose={choose}
                back={back}
                pay={() => setPayment(true)}
                navigate={navigate}
                download={download}
                openPanel={openPanel}
                chat={chatId ? activeChat || { title: "Чат поездки", kind: "general" } : null}
                chatError={activeChatError}
                retryChat={loadChat}
              />{panelKind && <TripOptions key={`options-${tripId}`} kind={panelKind} state={state} busy={busy || runningTrips.has(tripId)} choose={choose} close={closePanel} closing={panelClosing} changeKind={setPanelKind} discuss={discussPlan} pay={() => setPayment(true)} tripId={tripId} navigate={navigate} />}</div>
            )
          ) : page === "trips" ? (
            <Trips
              account={account}
              auth={() => setAuth(true)}
              trips={trips}
              navigate={navigate}
              run={run}
              reload={reloadTrips}
              removeTrip={removeTrip}
              busy={busy}
            />
          ) : page === "profile" ? (
            <Profile
              account={account}
              setAccount={(data) => {
                setAccount(data);
                if (!data) setDrafts({});
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
              discuss={discussSupport}
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
                discuss={discussSupport}
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
            <div className="empty-state"><h3>Страница не найдена</h3><p>Откройте диалог или выберите сохранённую поездку.</p><a className="primary" href="#plan">К диалогу с агентом</a></div>
          )}
        </main>
      </div>
      {auth && (
        <Auth
          close={() => setAuth(false)}
          authenticated={setAccount}
          run={run}
        />
      )}
      {chatDialog && <Modal title="Новый чат поездки" close={() => { if (!creatingChat) setChatDialog(null); }}>
        <p className="muted">Отдельный разговор с контекстом поездки. Обсуждение плана останется в своём чате.</p>
        <div className="chat-kind-picker">{[[LifeBuoy, "Помощь в пути", "support"], [MapPin, "Места и впечатления", "places"], [MessageCircle, "Другой вопрос", "general"]].map(([Component, title, kind]) => <button key={kind} className="secondary" aria-pressed={chatDialog.kind === kind} disabled={creatingChat} onClick={() => setChatDialog({ ...chatDialog, kind })}><Component size={17} />{title}</button>)}</div>
        <label className="field-label">Название чата<input value={chatTitle} maxLength={120} placeholder="Можно оставить пустым" disabled={creatingChat} onChange={(event) => setChatTitle(event.target.value)} /></label>
        {!tripId && <p>Выберите поездку:</p>}
        {!tripId && trips.map((trip) => <button key={trip.trip_id} className="chat-trip-choice secondary" disabled={creatingChat} onClick={() => createChat(trip.trip_id, chatDialog.kind, chatDialog.text, chatTitle)}><FolderOpen size={17} />{trip.state.constraints?.destination || "Новая поездка"} · {date(trip.state.constraints?.start)}</button>)}
        <div className="modal-actions"><button className="secondary" disabled={creatingChat} onClick={() => setChatDialog(null)}>Отмена</button><button className="primary" disabled={creatingChat} onClick={() => createChat(tripId, chatDialog.kind, chatDialog.text, chatTitle)}>{creatingChat ? <LoaderCircle className="spin" size={16} /> : <Plus size={16} />}{tripId ? "Создать чат" : "Создать для новой поездки"}</button></div>
      </Modal>}
      {chatToDelete && <Modal title="Удалить чат?" close={() => { if (!creatingChat) setChatToDelete(null); }}><p>Переписка «{chatToDelete.title}» будет удалена. План поездки и другие чаты сохранятся.</p><div className="modal-actions"><button className="secondary" disabled={creatingChat} onClick={() => setChatToDelete(null)}>Отмена</button><button className="primary danger-button" disabled={creatingChat || runningTrips.has(tripId + ":" + chatToDelete.chat_id)} onClick={async () => {
        setCreatingChat(true);
        await run(async () => { const id = chatToDelete.chat_id; await api(`/trips/${tripId}/chats/${id}`, { method: "DELETE" }); chatsVersion.current += 1; setChats((current) => current.filter((row) => row.chat_id !== id)); if (chatId === id) navigate("plan", tripId); setChatToDelete(null); });
        setCreatingChat(false);
      }}><Trash2 size={16} />Удалить чат</button></div></Modal>}
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
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
