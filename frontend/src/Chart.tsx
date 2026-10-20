import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { day, money } from "./money";
import type { ChartPoint } from "./types";

export default function BalanceChart({
  points,
  mini = false,
}: {
  points: ChartPoint[];
  mini?: boolean;
}) {
  if (!points.length)
    return <p className="muted chart-empty">Aucune donnée sur cette année.</p>;
  const data = points.map((p) => ({ ...p, euros: p.balance_cents / 100 }));
  return (
    <div
      className={mini ? "mini-chart" : "balance-chart"}
      role="img"
      aria-label={`Évolution du solde, de ${money(points[0].balance_cents)} à ${money(points.at(-1)!.balance_cents)}`}
    >
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <LineChart
          data={data}
          margin={
            mini
              ? { top: 5, bottom: 5, right: 5, left: 5 }
              : { top: 12, right: 24, left: 8, bottom: 4 }
          }
        >
          {!mini && (
            <CartesianGrid
              vertical={false}
              stroke="#e7ebe7"
              strokeDasharray="3 5"
            />
          )}
          {!mini && (
            <XAxis
              dataKey="date"
              tickFormatter={(value) =>
                new Date(`${value}T12:00:00`).toLocaleDateString("fr-FR", {
                  month: "short",
                })
              }
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 12, fill: "#718079" }}
              dy={10}
            />
          )}
          {!mini && (
            <YAxis
              tickFormatter={(value) => `${value} €`}
              width={85}
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 12, fill: "#718079" }}
            />
          )}
          {!mini && (
            <Tooltip
              formatter={(value) => [money(Number(value) * 100), "Solde"]}
              labelFormatter={(value) => day(String(value))}
              contentStyle={{ borderRadius: 12, border: "1px solid #e7ebe7" }}
            />
          )}
          <Line
            type="stepAfter"
            dataKey="euros"
            stroke="#327362"
            strokeWidth={mini ? 2 : 2.5}
            dot={data.length === 1 ? { r: 4 } : !mini}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
