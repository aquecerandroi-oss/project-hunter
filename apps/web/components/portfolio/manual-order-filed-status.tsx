import { Button } from "@/components/ui/button";
import { DialogClose } from "@/components/ui/dialog";
import { ManualOrderDecisionCard } from "@/components/portfolio/manual-order-decision-card";
import type { ManualOrderPollState } from "@/hooks/useManualOrderPoll";
import type { ManualOrderDetail, ManualOrderOut } from "@/lib/api/manual-orders-types";

export interface ManualOrderFiledStatusProps {
  filedOrder: ManualOrderOut;
  poll: ManualOrderPollState | null;
  onRetry: () => void;
  onClose: () => void;
}

/**
 * The post-submit half of `manual-order-form.tsx` (extracted so the form
 * component itself stays under the lint config's per-function line/complexity
 * budget): the optimistic "Enviada, aguardando decisão do motor" card, the
 * poll's own error/timeout states, and the `RiskDecision` once one exists.
 */
export function ManualOrderFiledStatus({ filedOrder, poll, onRetry, onClose }: ManualOrderFiledStatusProps) {
  const current: ManualOrderOut | ManualOrderDetail = poll?.order ?? filedOrder;

  return (
    <div className="flex flex-col gap-3 p-4">
      <p className="text-sm text-fg">{current.status === "pending" ? "Enviada, aguardando decisão do motor..." : "Decisão recebida."}</p>
      {poll?.error && <p className="text-sm text-red">Falha ao consultar a decisão: {poll.error}</p>}
      {poll?.timedOut && (
        <p className="text-sm text-warning">
          O motor não decidiu em 60s. A ordem continua registrada -- confira a tabela de propostas em instantes.
        </p>
      )}
      {current.decision && <ManualOrderDecisionCard decision={current.decision} />}
      <div className="flex justify-end gap-2">
        {current.status !== "pending" && (
          <Button type="button" variant="outline" size="sm" onClick={onRetry}>
            Enviar outra ordem
          </Button>
        )}
        <DialogClose asChild>
          <Button type="button" size="sm" onClick={onClose}>
            Fechar
          </Button>
        </DialogClose>
      </div>
    </div>
  );
}
