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
export const money = (value) =>
  value == null
    ? "Уточняется"
    : new Intl.NumberFormat("ru-RU", {
        style: "currency",
        currency: "RUB",
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
