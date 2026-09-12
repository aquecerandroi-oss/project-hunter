/**
 * The agreement matrix of today's cohort (T4.2d, `meme_graduation_matrix_v1`):
 * how many mints each of the four completion signals marked today (Brasília),
 * how many carry 1/2/3/4 of them, and -- in amber, never hidden -- how many
 * pairs disagree and how many are "REST diz completa" and nothing else (the
 * 77 of 140 the plantão measured). Real counts only: no row for today
 * renders "sem sinal hoje ainda", never a strip of zeros.
 */
import { COMPLETION_SIGNAL_KEYS, memeCompletionSignalLabel } from "./labels";
import { type GraduationMatrix, matrixDisagreements } from "./meme-graduation-signals";

function Count({ label, value, tone = "fg" }: { label: string; value: number; tone?: "fg" | "warning" }) {
  return (
    <div className="flex flex-col gap-1 rounded-md border border-border p-3">
      <span className="text-[11px] font-medium uppercase tracking-wide text-fg-muted">{label}</span>
      <span className={`text-xl font-semibold tabular-nums ${tone === "warning" ? "text-warning" : "text-fg"}`}>{value.toLocaleString("pt-BR")}</span>
    </div>
  );
}

const MATRIX_COUNT: Record<(typeof COMPLETION_SIGNAL_KEYS)[number], keyof GraduationMatrix> = {
  rest_complete: "rest_complete",
  curve_filled: "curve_filled",
  graduated_board: "graduated_board",
  pool_created: "pool_created",
};

export interface MemeGraduationStripProps {
  matrix: GraduationMatrix | null | undefined;
}

export function MemeGraduationStrip({ matrix }: MemeGraduationStripProps) {
  if (!matrix) {
    return (
      <section className="flex flex-col gap-1">
        <h2 className="text-sm font-medium text-fg">Graduação hoje — quatro sinais separados</h2>
        <p className="text-xs text-fg-muted">Sem sinal de conclusão hoje ainda (nenhum mint da coorte marcou REST, curva cheia, board graduated ou pool).</p>
      </section>
    );
  }
  const disagreeing = matrixDisagreements(matrix);
  return (
    <section className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-medium text-fg">Graduação hoje — quatro sinais separados</h2>
        <p className="text-xs text-fg-muted">
          {matrix.mints.toLocaleString("pt-BR")} mint(s) com ao menos um sinal · {matrix.completed.toLocaleString("pt-BR")} concluído(s) pela regra (o mais antigo dos
          quatro; REST com reserva zero não conta sozinho)
        </p>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {COMPLETION_SIGNAL_KEYS.map((key) => (
          <Count key={key} label={memeCompletionSignalLabel(key)} value={matrix[MATRIX_COUNT[key]] as number} />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Count label="1 sinal" value={matrix.signals_1} />
        <Count label="2 sinais" value={matrix.signals_2} />
        <Count label="3 sinais" value={matrix.signals_3} />
        <Count label="4 sinais" value={matrix.signals_4} />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Count label="pares que discordam" value={disagreeing} tone={disagreeing > 0 ? "warning" : "fg"} />
        <Count label="só REST, sem veredito" value={matrix.rest_only_unclassified} tone={matrix.rest_only_unclassified > 0 ? "warning" : "fg"} />
      </div>
      <p className="text-[11px] text-fg-subtle">
        Dia de Brasília do sinal mais antigo de cada mint ({matrix.day_brt}). Pares: REST×cheia {matrix.disagree_rest_filled} · REST×board {matrix.disagree_rest_board} · REST×pool{" "}
        {matrix.disagree_rest_pool} · cheia×board {matrix.disagree_filled_board} · cheia×pool {matrix.disagree_filled_pool} · board×pool {matrix.disagree_board_pool}.
      </p>
    </section>
  );
}
