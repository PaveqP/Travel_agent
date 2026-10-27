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
    seen.add(key);
    const region = regions.find(([pattern]) =>
      pattern.test(place.area || place.destination || ""),
    );
    const lon = place.coordinates?.lon ?? region?.[1];
    const lat = place.coordinates?.lat ?? region?.[2];
    if (
      !Number.isFinite(lon) ||
      !Number.isFinite(lat) ||
      lon < 39.5 ||
      lon > 40.4 ||
      lat < 43.34 ||
      lat > 43.85
    )
      return [];
    return [
      {
        id: key,
        name: place.name,
        area: place.area || place.destination,
        x: (lon - 39.5) * 1000,
        y: (43.85 - lat) * 900,
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
export function tripStatus(
  state,
  today = new Date().toLocaleDateString("en-CA", { timeZone: "Europe/Moscow" }),
) {
  if (state?.stage !== "booked") return "Планируем";
  const c = state.constraints || {};
  if (c.end && c.end < today) return "Воспоминания";
  if (c.start && c.start <= today) return "В путешествии";
  return "Скоро в путь";
}

export const party = (adults, childrenAges = []) =>
  `${adults ?? "—"} взрослых${childrenAges.length ? `; дети (возраст): ${childrenAges.join(", ")}` : ""}`;
