/**
 * T4.10b: the trend lines drawn over the mcap curve (`meme-curve-chart.tsx`)
 * and the sentence under it. The geometry is `meme-lines.ts` (pure, in data
 * space); this file only maps it with the scale functions the chart hands in
 * and picks the semantic colors (docs/DESIGN.md §2: green only with meaning
 * -- the support line is green when the lows are rising, neutral otherwise;
 * the previous window's high is `info`; the breakout is a green dot; never
 * gold inside a chart).
 */
import { formatSol } from "./meme-format";
import { type BreakoutMark, type HorizontalLine, hypeText, type LineOverlay, lineReadingText, type SupportSegment } from "./meme-lines";

interface Scale {
  /** Same time scale as the curve; `null` outside the drawn span (it cannot be, by construction, but the guard costs nothing). */
  toX: (x: number) => number | null;
  toY: (y: number) => number;
}

function PreviousHighLine({ line, toX, toY }: { line: HorizontalLine } & Scale) {
  const x1 = toX(line.x1);
  const x2 = toX(line.x2);
  if (x1 === null || x2 === null) return null;
  return (
    <line data-line="previous-high" x1={x1} x2={x2} y1={toY(line.y)} y2={toY(line.y)} className="text-info" stroke="currentColor" strokeWidth={1} strokeDasharray="4 2">
      <title>{`máxima 15 min da janela anterior: ${formatSol(line.yText)}`}</title>
    </line>
  );
}

function SupportLine({ segment, toX, toY }: { segment: SupportSegment } & Scale) {
  const x1 = toX(segment.x1);
  const x2 = toX(segment.x2);
  if (x1 === null || x2 === null) return null;
  const rising = segment.higherLows === true;
  return (
    <line data-line="support" x1={x1} x2={x2} y1={toY(segment.y1)} y2={toY(segment.y2)} className={rising ? "text-green" : "text-fg-muted"} stroke="currentColor" strokeWidth={1}>
      <title>{rising ? "suporte pelos dois últimos fundos (ascendentes)" : "suporte pelos dois últimos fundos"}</title>
    </line>
  );
}

function BreakoutDot({ mark, toX, toY }: { mark: BreakoutMark } & Scale) {
  if (mark.y === null) return null;
  const x = toX(mark.x);
  if (x === null) return null;
  return (
    <circle data-line="breakout" cx={x} cy={toY(mark.y)} r={3} className="text-green" fill="currentColor">
      <title>rompimento da máxima de 15 min</title>
    </circle>
  );
}

export interface CurveLinesLayerProps extends Scale {
  overlay: LineOverlay;
}

/** SVG group with the support segment, the previous 15-minute high and the breakout mark -- nothing when the reading is not `traced`. */
export function CurveLinesLayer({ overlay, toX, toY }: CurveLinesLayerProps) {
  return (
    <g>
      {overlay.previousHigh && <PreviousHighLine line={overlay.previousHigh} toX={toX} toY={toY} />}
      {overlay.support && <SupportLine segment={overlay.support} toX={toX} toY={toY} />}
      {overlay.breakout && <BreakoutDot mark={overlay.breakout} toX={toX} toY={toY} />}
    </g>
  );
}

export interface CurveLinesCaptionProps {
  overlay: LineOverlay;
}

/** The reading in words: one line for the trend lines, one for the hype score -- both name their absence instead of hiding it. */
export function CurveLinesCaption({ overlay }: CurveLinesCaptionProps) {
  const { reading, previousHigh, breakout } = overlay;
  const traced = reading.kind === "traced";
  const extras: string[] = [];
  if (traced) {
    extras.push(previousHigh ? `máxima 15 min anterior ${formatSol(previousHigh.yText)}` : "máxima 15 min anterior: sem janela anterior");
    if (breakout?.unplaced) extras.push("rompimento sem mcap no minuto para posicionar a marca");
  }
  const text = [lineReadingText(reading), ...extras].join(" · ");
  return (
    <div className="mt-1 flex flex-col gap-0.5 text-[11px]">
      <p className={traced ? "text-fg-muted" : "text-fg-subtle"}>{text}</p>
      {traced && <p className="text-fg-subtle">linhas: suporte pelos dois últimos fundos (cheia) · máxima 15 min da janela anterior (tracejada) · rompimento (ponto)</p>}
      <p className="text-fg-subtle">{hypeText(overlay.hype)}</p>
    </div>
  );
}
