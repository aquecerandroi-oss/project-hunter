/**
 * Brief T3.24b item [4]: rewritten in plain language, no backstage (script
 * path, task id) -- the honest fact a reader needs is that versions are
 * activated by the operator, not that a specific script exists.
 */
export function LabVersionsEmpty() {
  return (
    <div className="rounded-lg border border-dashed border-border bg-bg-elevated p-10 text-center">
      <p className="text-sm text-fg">Nenhuma versão de estratégia ativa nesta janela e coorte.</p>
      <p className="mt-1 text-sm text-fg-muted">
        Zero versões é um resultado, não uma falha -- versões são ativadas pelo operador, fora desta tela.
      </p>
    </div>
  );
}
