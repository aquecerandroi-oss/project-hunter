export interface LabSignalsEmptyProps {
  cohort: string;
}

/** "0 sinais nesta janela" is itself a result (brief S3b), never rendered as if the fetch had failed. */
export function LabSignalsEmpty({ cohort }: LabSignalsEmptyProps) {
  return (
    <div className="rounded-lg border border-dashed border-border bg-bg-elevated p-10 text-center">
      <p className="text-sm text-fg">0 sinais nesta seleção.</p>
      <p className="mt-1 text-sm text-fg-muted">
        Cohort &quot;{cohort}&quot; e os filtros de versão/mercado ativos não têm nenhum sinal registrado -- isto é um
        resultado real, não uma falha de leitura.
      </p>
    </div>
  );
}
