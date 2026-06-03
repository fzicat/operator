"use client";

import { useRef, useState } from "react";

export interface OPChartPoint {
  date: string; // YYYY-MM-DD
  total: number;
}

interface Props {
  /** Chronological (oldest -> newest) Total OP series. */
  data: OPChartPoint[];
  /** SMA window length. */
  smaWindow?: number;
}

const VIEW_W = 900;
const VIEW_H = 300;
const M = { top: 16, right: 16, bottom: 28, left: 64 };

function formatAxis(value: number): string {
  return Math.round(value).toLocaleString("en-US");
}

/**
 * Simple moving average. Entries before a full window are null so the line
 * only starts once `window` points are available.
 */
function simpleMovingAverage(values: number[], window: number): (number | null)[] {
  return values.map((_, i) => {
    if (i < window - 1) return null;
    let sum = 0;
    for (let j = i - window + 1; j <= i; j++) sum += values[j];
    return sum / window;
  });
}

export function OutstandingPremiumChart({ data, smaWindow = 7 }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);

  if (data.length === 0) return null;

  const totals = data.map((d) => d.total);
  const sma = simpleMovingAverage(totals, smaWindow);

  const plotW = VIEW_W - M.left - M.right;
  const plotH = VIEW_H - M.top - M.bottom;

  const seriesValues = [...totals, ...sma.filter((v): v is number => v !== null)];
  let yMin = Math.min(0, ...seriesValues);
  let yMax = Math.max(0, ...seriesValues);
  if (yMin === yMax) {
    yMin -= 1;
    yMax += 1;
  }
  // 6% headroom
  const pad = (yMax - yMin) * 0.06;
  yMin -= pad;
  yMax += pad;

  const n = data.length;
  const xFor = (i: number) => M.left + (n === 1 ? plotW / 2 : (plotW * i) / (n - 1));
  const yFor = (v: number) => M.top + plotH * (1 - (v - yMin) / (yMax - yMin));

  const totalLine = totals.map((v, i) => `${xFor(i)},${yFor(v)}`).join(" ");
  const smaLine = sma
    .map((v, i) => (v === null ? null : `${xFor(i)},${yFor(v)}`))
    .filter((p): p is string => p !== null)
    .join(" ");

  // y-axis ticks
  const tickCount = 4;
  const yTicks = Array.from({ length: tickCount + 1 }, (_, k) => yMin + ((yMax - yMin) * k) / tickCount);

  // x-axis labels (~6 evenly spaced)
  const xTickEvery = Math.max(1, Math.ceil(n / 6));
  const xTickIdx = data.map((_, i) => i).filter((i) => i % xTickEvery === 0 || i === n - 1);

  const handleMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const xPx = ((e.clientX - rect.left) / rect.width) * VIEW_W;
    const ratio = (xPx - M.left) / plotW;
    const i = Math.round(ratio * (n - 1));
    setHover(Math.max(0, Math.min(n - 1, i)));
  };

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
      className="w-full h-auto select-none"
      onMouseMove={handleMove}
      onMouseLeave={() => setHover(null)}
      role="img"
      aria-label="Outstanding premium over time"
    >
      {/* y grid + labels */}
      {yTicks.map((t, k) => {
        const y = yFor(t);
        return (
          <g key={k}>
            <line
              x1={M.left}
              x2={VIEW_W - M.right}
              y1={y}
              y2={y}
              style={{ stroke: "var(--gruvbox-bg3)" }}
              strokeWidth={1}
            />
            <text
              x={M.left - 8}
              y={y + 4}
              textAnchor="end"
              fontSize={12}
              style={{ fill: "var(--gruvbox-fg4)" }}
            >
              {formatAxis(t)}
            </text>
          </g>
        );
      })}

      {/* x labels */}
      {xTickIdx.map((i) => (
        <text
          key={i}
          x={xFor(i)}
          y={VIEW_H - 8}
          textAnchor="middle"
          fontSize={12}
          style={{ fill: "var(--gruvbox-fg4)" }}
        >
          {data[i].date.slice(5)}
        </text>
      ))}

      {/* SMA line */}
      {smaLine && (
        <polyline
          points={smaLine}
          fill="none"
          style={{ stroke: "var(--gruvbox-blue)" }}
          strokeWidth={2}
          strokeDasharray="5 4"
        />
      )}

      {/* Total OP line */}
      <polyline
        points={totalLine}
        fill="none"
        style={{ stroke: "var(--gruvbox-yellow)" }}
        strokeWidth={2}
      />

      {/* hover */}
      {hover !== null && (
        <g>
          <line
            x1={xFor(hover)}
            x2={xFor(hover)}
            y1={M.top}
            y2={M.top + plotH}
            style={{ stroke: "var(--gruvbox-fg4)" }}
            strokeWidth={1}
            strokeDasharray="3 3"
          />
          <circle cx={xFor(hover)} cy={yFor(totals[hover])} r={3.5} style={{ fill: "var(--gruvbox-yellow)" }} />
          {sma[hover] !== null && (
            <circle cx={xFor(hover)} cy={yFor(sma[hover] as number)} r={3.5} style={{ fill: "var(--gruvbox-blue)" }} />
          )}
          {(() => {
            const boxW = 150;
            const boxH = 58;
            const cx = xFor(hover);
            const bx = Math.min(Math.max(cx + 10, M.left), VIEW_W - M.right - boxW);
            const by = M.top + 4;
            const smaVal = sma[hover];
            return (
              <g>
                <rect
                  x={bx}
                  y={by}
                  width={boxW}
                  height={boxH}
                  rx={4}
                  style={{ fill: "var(--gruvbox-bg-hard)", stroke: "var(--gruvbox-bg3)" }}
                />
                <text x={bx + 8} y={by + 18} fontSize={12} style={{ fill: "var(--gruvbox-fg)" }}>
                  {data[hover].date}
                </text>
                <text x={bx + 8} y={by + 34} fontSize={12} style={{ fill: "var(--gruvbox-yellow)" }}>
                  Total OP: {formatAxis(totals[hover])}
                </text>
                <text x={bx + 8} y={by + 50} fontSize={12} style={{ fill: "var(--gruvbox-blue)" }}>
                  {smaWindow} SMA: {smaVal === null ? "-" : formatAxis(smaVal)}
                </text>
              </g>
            );
          })()}
        </g>
      )}

      {/* legend */}
      <g>
        <line x1={M.left} x2={M.left + 20} y1={M.top + 4} y2={M.top + 4} style={{ stroke: "var(--gruvbox-yellow)" }} strokeWidth={2} />
        <text x={M.left + 26} y={M.top + 8} fontSize={12} style={{ fill: "var(--gruvbox-fg4)" }}>
          Total OP
        </text>
        <line x1={M.left + 100} x2={M.left + 120} y1={M.top + 4} y2={M.top + 4} style={{ stroke: "var(--gruvbox-blue)" }} strokeWidth={2} strokeDasharray="5 4" />
        <text x={M.left + 126} y={M.top + 8} fontSize={12} style={{ fill: "var(--gruvbox-fg4)" }}>
          {smaWindow} SMA
        </text>
      </g>
    </svg>
  );
}
