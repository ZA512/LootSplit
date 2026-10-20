const currency = new Intl.NumberFormat("fr-FR", {
  style: "currency",
  currency: "EUR",
});
export const money = (cents: number) => currency.format(cents / 100);
export const signedMoney = (cents: number) =>
  `${cents > 0 ? "+" : ""}${money(cents)}`;
export const day = (value: string) =>
  new Intl.DateTimeFormat("fr-FR", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(`${value.slice(0, 10)}T12:00:00`));
export const localDate = () => {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
};
export function cents(value: string): number {
  const normalized = value.replace(/[\s\u00a0\u202f]/g, "").replace(",", ".");
  if (!/^-?\d+(\.\d{1,2})?$/.test(normalized))
    throw new Error("Saisissez un montant avec deux décimales au maximum.");
  const negative = normalized.startsWith("-");
  const [whole, fraction = ""] = normalized.replace("-", "").split(".");
  const result = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  if (!Number.isSafeInteger(result) || result > 10 ** 12)
    throw new Error("Ce montant est trop élevé.");
  return negative ? -result : result;
}
