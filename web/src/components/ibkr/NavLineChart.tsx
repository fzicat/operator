"use client";

import { useRef, useState } from "react";

export interface NavLinePoint {
  date: string; // YYYY-MM-DD
  value: number;
}

interface Props {
  /** Chronological (oldest -> newest) series. */
  data: NavLinePoint[];
  /** Line color (CSS value, e.g. a gruvbox variable). */
  color: string;
  /** Label shown in the hover tooltip. */
  valueLabel: string;
  /** Always include y=0 in the domain and draw a baseline there. */
  zeroLine?: boolean;
}

const VIEW_W = 900;
const VIEW_H = 300;
const M = { top: 16, right: 16, bottom: 28, left: 64 };

function formatAxis(value: number): string {
  return Math.round(value).toLocaleString("en-US");
}

export function NavLineChart({ data, color, valueLabel, zeroLine = false }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);

  if (data.length === 0) return null;

  const values = data.map((d) => d.value);

  const plotW = VIEW_W - M.left - M.right;
  const plotH = VIEW_H - M.top - M.bottom;

  let yMin = Math.min(...values, ...(zeroLine ? [0] : []));
  let yMax = Math.max(...values, ...(zeroLine ? [0] : []));
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

  const line = values.map((v, i) => `${xFor(i)},${yFor(v)}`).join(" ");

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

      {/* zero baseline */}
      {zeroLine && (
        <line
          x1={M.left}
          x2={VIEW_W - M.right}
          y1={yFor(0)}
          y2={yFor(0)}
          style={{ stroke: "var(--gruvbox-fg4)" }}
          strokeWidth={1}
        />
      )}

      {/* value line */}
      <polyline points={line} fill="none" style={{ stroke: color }} strokeWidth={2} />

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
          <circle cx={xFor(hover)} cy={yFor(values[hover])} r={3.5} style={{ fill: color }} />
          {(() => {
            const boxW = 150;
            const boxH = 42;
            const cx = xFor(hover);
            const bx = Math.min(Math.max(cx + 10, M.left), VIEW_W - M.right - boxW);
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
                <text x={bx + 8} y={by + 34} fontSize={12} style={{ fill: color }}>
                  {valueLabel}: {formatAxis(values[hover])}
                </text>
              </g>
            );
          })()}
        </g>
      )}
    </svg>
  );
}
