export const stages = [
  "scenarios",
  "transport",
  "stays",
  "itinerary",
  "review",
  "booked",
];
export const stageNames = [
  "Идея",
  "Билеты",
  "Отель",
  "Программа",
  "Проверка",
  "Готово",
];
export const money = (value, currency = "RUB") =>
  value == null
    ? "Уточняется"
    : new Intl.NumberFormat("ru-RU", {
        style: "currency",
        currency,
        maximumFractionDigits: 0,
      }).format(Number(value));
export const date = (value) =>
  value
    ? new Intl.DateTimeFormat("ru-RU", {
        day: "numeric",
        month: "short",
      }).format(new Date(value.slice(0, 10) + "T12:00:00"))
    : "Даты уточняются";
export const time = (value) => (value ? value.slice(11, 16) : "—:—");
export const pendingText = (messages, text) =>
  messages.at(-1)?.role === "user" && messages.at(-1)?.text === text ? "" : text;
export const basis = (value) =>
  ({
    party: "за всех",
    person: "за человека",
    ticket: "за билет",
    room_stay: "за проживание",
    unknown: "основа цены не подтверждена",
  })[value] || "основа цены не подтверждена";
export const safeUrl = (value) => {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) &&
      !url.username &&
      !url.password
      ? url.href
      : null;
  } catch {
    return null;
  }
};
export function messageLinks(text) {
  const parts = [];
  const pattern = /\[([^\]\n]+)\]\((https?:\/\/(?:[^\s()]|\([^()\s]*\))+)\)|https?:\/\/[^\s<>\[\]]+/g;
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > cursor) parts.push({ text: text.slice(cursor, match.index) });
    let url = match[2] || match[0].replace(/[.,!?;:]+$/, "");
    if (!match[2]) {
      while (url.endsWith(")") && (url.match(/\)/g) || []).length > (url.match(/\(/g) || []).length)
        url = url.slice(0, -1);
    }
    const href = safeUrl(url);
    const length = match[2] ? match[0].length : url.length;
    parts.push({ text: href ? match[1] || url : match[0].slice(0, length), href });
    cursor = match.index + length;
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor) });
  return parts;
}

export function transportRoutes(candidate = {}) {
  const fallback = [
    {
      origin: candidate.origin,
      destination: candidate.destination,
      departure_at: candidate.departure_at,
      arrival_at: candidate.arrival_at,
      start: candidate.start,
      duration_minutes: candidate.duration_minutes,
      transfers: candidate.transfers,
    },
    {
      origin: candidate.destination,
      destination: candidate.origin,
      departure_at: candidate.return_departure_at,
      arrival_at: candidate.return_arrival_at,
      start: candidate.end,
    },
  ];
  return candidate.legs?.length >= 2 ? candidate.legs
    : candidate.legs?.length === 1 ? [candidate.legs[0], fallback[1]] : fallback;
}

export function currentOption(state) {
  return (
    state?.options?.find((o) => o.id === state.selected) || state?.options?.[0]
  );
}
export function tripParts(state) {
  const option = currentOption(state);
  const receipt = state?.stage === "booked" ? state.receipt : null;
  const candidates = Object.values(state?.results || {}).flatMap(
    (result) => result.candidates || [],
  );
  const bookedItem = (kind) => {
    const item = receipt?.items?.find((item) => item.kind === kind);
    return item ? { ...item.details, ...item } : null;
  };
  return {
    transport: receipt
      ? bookedItem("transport")
      : candidates.find((item) => item.id === state?.selected_transport) ||
        option?.transport,
    stay: receipt
      ? bookedItem("stays")
      : candidates.find((item) => item.id === state?.selected_stay) ||
        option?.stay,
    days: receipt?.itinerary || option?.days || [],
    total: receipt?.payment?.amount ?? option?.budget?.known_subtotal,
  };
}

export function tripMapPoints(state) {
  const { transport, stay, days } = tripParts(state);
  const places = [
    transport,
    stay,
    ...days.flatMap((day) => day.candidates || []),
  ].filter(Boolean);
  const regions = [
    [/Полян|Хутор/i, 40.2, 43.68],
    [/Сириус|Имеретин/i, 39.98, 43.4],
    [/Адлер/i, 39.92, 43.43],
    [/Сочи/i, 39.72, 43.6],
  ];
  const seen = new Set();
  return places.flatMap((place) => {
    const key = place.id || place.source_id || place.name;
    if (seen.has(key)) return [];
    const region = regions.find(([pattern]) =>
      pattern.test(place.area || place.destination || ""),
    );
    const lon = place.coordinates ? place.coordinates.lon : region?.[1];
    const lat = place.coordinates ? place.coordinates.lat : region?.[2];
    if (
      !Number.isFinite(lon) ||
      !Number.isFinite(lat) ||
      lon < -180 ||
      lon > 180 ||
      lat < -90 ||
      lat > 90
    )
      return [];
    seen.add(key);
    return [
      {
        id: key,
        name: place.name,
        area: place.area || place.destination,
        lon,
        lat,
        approximate: !place.coordinates,
        kind:
          place === transport
            ? "transport"
            : place === stay
              ? "stay"
              : "experience",
      },
    ];
  });
}

export function tripMapUrls(points, activeId = null) {
  const selected = points.find((point) => point.id === activeId);
  const visible = selected ? [selected] : points;
  const params = new URLSearchParams({ lang: "ru_RU", l: "map" });
  if (visible.length) {
    params.set("pt", visible.map((point) => `${point.lon},${point.lat}`).join("~"));
    if (selected || visible.length === 1) {
      const point = visible[0];
      params.set("ll", `${point.lon},${point.lat}`);
      params.set("z", point.approximate ? "12" : "16");
    } else {
      const lons = visible.map((point) => point.lon);
      const lats = visible.map((point) => point.lat);
      const west = Math.min(...lons), east = Math.max(...lons);
      const south = Math.min(...lats), north = Math.max(...lats);
      const padLon = Math.max((east - west) * 0.2, 0.008);
      const padLat = Math.max((north - south) * 0.2, 0.008);
      params.set("bbox", `${west - padLon},${south - padLat}~${east + padLon},${north + padLat}`);
    }
  } else {
    params.set("ll", "95,62");
    params.set("z", "3");
  }
  return {
    embed: `https://yandex.ru/map-widget/v1/?${params}`,
    external: `https://yandex.ru/maps/?${params}`,
  };
}
export function tripStatus(
  state,
  today = new Date().toLocaleDateString("en-CA", { timeZone: "Europe/Moscow" }),
) {
  if (state?.stage !== "booked") {
    if (state?.autonomous) {
      if (state.selected) return "Вариант выбран";
      if (state.status === "partial") return "План требует уточнений";
      if (state.focus === "stays" && state.cards?.length)
        return "Отели найдены";
      if (state.options?.length) return "Варианты готовы";
    }
    return "Планируем";
  }
  const c = state.constraints || {};
  if (c.end && c.end < today) return "Воспоминания";
  if (c.start && c.start <= today) return "В путешествии";
  return "Скоро в путь";
}

export function canCheckout(state, now = Date.now()) {
  const option = state?.options?.find((item) => item.id === state.selected);
  return (
    state?.stage === "review" &&
    !!option &&
    option.revision === state.revision &&
    [option.transport, option.stay].every(
      (item) =>
        item?.price != null &&
        item.source?.evidence === "live" &&
        new Date(item.source.expires_at).getTime() > now,
    )
  );
}

export function feedbackText(feedback) {
  return (
    {
      no_transport: "Не удалось подтвердить билеты на подходящие даты.",
      no_stays: "Не удалось подтвердить проживание на выбранные даты.",
      arrival_stay_mismatch:
        "Нужно согласовать даты отеля с прибытием и выездом.",
      no_day_plan: "Программа по дням пока не подтверждена.",
      program_update_incomplete: "Прежняя программа сохранена, но последнее изменение пока не удалось применить.",
      invalid_day_evidence: "Часть мест в программе требует проверки.",
      empty_program: "Пока не найдены подходящие занятия на дни поездки.",
      mountain_days_mismatch: "Нужно уточнить число дней в горах.",
      ski_program_mismatch:
        "Программа пока не соответствует горнолыжному отдыху.",
    }[feedback.code] || "Часть поездки требует уточнения с агентом."
  );
}

export const party = (adults, childrenAges = []) =>
  `${adults ?? "—"} взрослых${childrenAges.length ? `; дети (возраст): ${childrenAges.join(", ")}` : ""}`;
