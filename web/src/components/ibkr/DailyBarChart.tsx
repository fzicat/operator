"use client";

import { useRef, useState } from "react";

export interface BarChartPoint {
  date: string; // YYYY-MM-DD
  value: number;
}

interface Props {
  /** Chronological (oldest -> newest) series. */
  data: BarChartPoint[];
  /**
   * Bar coloring: "sign" colors positive bars green and negative bars red;
   * any other string is used verbatim as the fill for every bar (e.g. a
   * gruvbox CSS variable).
   */
  color?: "sign" | string;
  /** Label shown for the value in the hover tooltip. */
  valueLabel?: string;
}

const VIEW_W = 900;
const VIEW_H = 300;
const M = { top: 16, right: 16, bottom: 28, left: 64 };

function formatAxis(value: number): string {
  return Math.round(value).toLocaleString("en-US");
}

export function DailyBarChart({ data, color = "sign", valueLabel = "Value" }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);

  if (data.length === 0) return null;

  const values = data.map((d) => d.value);

  const plotW = VIEW_W - M.left - M.right;
  const plotH = VIEW_H - M.top - M.bottom;

  let yMin = Math.min(0, ...values);
  let yMax = Math.max(0, ...values);
  if (yMin === yMax) {
    yMin -= 1;
    yMax += 1;
  }
  // 6% headroom
  const pad = (yMax - yMin) * 0.06;
  yMin -= pad;
  yMax += pad;

  const n = data.length;
  const slotW = plotW / n;
  const barW = slotW * 0.7;
  const xCenter = (i: number) => M.left + slotW * (i + 0.5);
  const yFor = (v: number) => M.top + plotH * (1 - (v - yMin) / (yMax - yMin));
  const zeroY = yFor(0);

  const fillFor = (v: number) =>
    color === "sign"
      ? v >= 0
        ? "var(--gruvbox-green)"
        : "var(--gruvbox-red)"
      : color;

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
    const i = Math.floor((xPx - M.left) / slotW);
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
      aria-label={`${valueLabel} over time`}
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

      {/* zero baseline */}
      <line
        x1={M.left}
        x2={VIEW_W - M.right}
        y1={zeroY}
        y2={zeroY}
        style={{ stroke: "var(--gruvbox-fg4)" }}
        strokeWidth={1}
      />

      {/* bars */}
      {data.map((d, i) => {
        const yv = yFor(d.value);
        const top = Math.min(yv, zeroY);
        const h = Math.abs(yv - zeroY);
        return (
          <rect
            key={d.date}
            x={xCenter(i) - barW / 2}
            y={top}
            width={barW}
            height={h}
            style={{ fill: fillFor(d.value), opacity: hover === null || hover === i ? 1 : 0.55 }}
          />
        );
      })}

      {/* x labels */}
      {xTickIdx.map((i) => (
        <text
          key={i}
          x={xCenter(i)}
          y={VIEW_H - 8}
          textAnchor="middle"
          fontSize={12}
          style={{ fill: "var(--gruvbox-fg4)" }}
        >
          {data[i].date.slice(5)}
        </text>
      ))}

      {/* hover */}
      {hover !== null && (
        <g>
          {(() => {
            const boxW = 150;
            const boxH = 42;
            const cx = xCenter(hover);
            const bx = Math.min(Math.max(cx - boxW / 2, M.left), VIEW_W - M.right - boxW);
            const by = M.top + 4;
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
                <text x={bx + 8} y={by + 34} fontSize={12} style={{ fill: fillFor(data[hover].value) }}>
                  {valueLabel}: {formatAxis(data[hover].value)}
                </text>
              </g>
            );
          })()}
        </g>
      )}
    </svg>
  );
}
