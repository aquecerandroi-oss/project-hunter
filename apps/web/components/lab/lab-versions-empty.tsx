export function LabVersionsEmpty() {
  return (
    <div className="rounded-lg border border-dashed border-border bg-bg-elevated p-10 text-center">
      <p className="text-sm text-fg">Nenhuma versão de estratégia ativada ainda nesta janela/coorte.</p>
      <p className="mt-1 text-sm text-fg-muted">
        0 versões é um resultado, não uma falha -- o `strategy-worker` só ativa uma versão por script auditado
        (`infra/scripts/activate_strategy_version.py`) após os critérios S0-S2 do plano do Shadow Lab.
      </p>
    </div>
  );
}
