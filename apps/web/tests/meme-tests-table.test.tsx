import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { MemeTestsCards } from "@/components/meme-tests/meme-tests-cards";
import { MemeTestsTable } from "@/components/meme-tests/meme-tests-table";
import { MemeTestsTotals } from "@/components/meme-tests/meme-tests-totals";

import { realRow, testRow, testsPayload } from "./meme-tests-fixtures";

afterEach(cleanup);

describe("MemeTestsTable (dense record)", () => {
  it("renders the ten primary columns, Brasília with seconds, the exit reason and the REAL badge", () => {
    render(<MemeTestsTable orgSlug="ever" rows={[testRow(), realRow()]} />);
    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["", "Hora entrada", "Moeda", "Conjunto", "Entrada SOL", "Saída SOL", "PnL SOL", "PnL US$", "R", "Motivo", "Duração"]);
    expect(screen.getByText("11:00:05")).toBeInTheDocument();
    expect(screen.getByTitle("12/09/2026 11:00:05")).toBeInTheDocument();
    expect(screen.getByText("alvo atingido")).toBeInTheDocument();
    expect(screen.getByText("+0.1800 SOL")).toBeInTheDocument();
    expect(screen.getByText("+US$ 32.58")).toBeInTheDocument();
    expect(screen.getByText("0.90 R")).toBeInTheDocument();
    expect(screen.getByText("7 min 25 s")).toBeInTheDocument();
    expect(screen.getByText("REAL — observado na cadeia")).toBeInTheDocument();
    expect(screen.getByText("REAL · carteira 6nAh8drz")).toBeInTheDocument();
    expect(screen.getByText("sem cotação")).toBeInTheDocument();
  });

  it("expands a row in place with the two photographs and what the Lab said", () => {
    render(<MemeTestsTable orgSlug="ever" rows={[testRow()]} />);
    expect(screen.queryByText("O que o Lab dizia no minuto da entrada")).not.toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: "expandir detalhes" });
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const detail = screen.getByText("O que o Lab dizia no minuto da entrada").closest("div");
    expect(detail).not.toBeNull();
    expect(screen.getByText("0.00000003 SOL/token")).toBeInTheDocument();
    expect(screen.getByText("6,443,000")).toBeInTheDocument();
    expect(screen.getByText("40 s · 1 fotografia(s)")).toBeInTheDocument();
    expect(screen.getByText("Linha traçável?")).toBeInTheDocument();
    expect(screen.getByText("0.7 (parcial)")).toBeInTheDocument();
    expect(screen.getByText("progress_gate, age_gate")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "ficha da aposta" })).toHaveAttribute("href", "/ever/meme/mesa/aposta/bet-1");
    fireEvent.click(screen.getByRole("button", { name: "recolher detalhes" }));
    expect(screen.queryByText("O que o Lab dizia no minuto da entrada")).not.toBeInTheDocument();
  });

  it("marks a provisional exit and a provisional US$ with an asterisk, and a manual bet says it has no Lab minute", () => {
    const open = testRow({
      id: "open-1",
      status: "open",
      exit: { ...testRow().exit, provisional: true, reason: null, reason_label: "aberta — marca atual (saída provisória)", sol_received: "0.25" },
      pnl_sol: "0.05",
      pnl_usd: "8.95",
      pnl_usd_basis: "entry_quote_provisional",
      lab_context: { ...testRow().lab_context, reason: "manual_no_minute", features_end_time: null, features_version: null },
    });
    render(<MemeTestsTable orgSlug="ever" rows={[open]} />);
    expect(screen.getByText("0.2500 SOL *")).toBeInTheDocument();
    expect(screen.getByText("+US$ 8.95 *")).toBeInTheDocument();
    expect(screen.getByText("aberta — marca atual (saída provisória)")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "expandir detalhes" }));
    expect(screen.getByText("compra manual — não nasceu de um minuto do Lab")).toBeInTheDocument();
  });
});

describe("MemeTestsCards (375 px)", () => {
  it("one card per row with the six numbers and a native details block", () => {
    render(<MemeTestsCards orgSlug="ever" rows={[testRow(), realRow()]} />);
    const [first, second, ...rest] = screen.getAllByRole("listitem");
    if (!first || !second) throw new Error("expected two cards");
    expect(rest).toHaveLength(0);
    expect(within(first).getByText("11:00:05")).toBeInTheDocument();
    expect(within(first).getByText("Detalhes")).toBeInTheDocument();
    expect(within(second).getByText("REAL — observado na cadeia")).toBeInTheDocument();
  });
});

describe("MemeTestsTotals", () => {
  it("shows the day's counts, PnL in SOL and US$, R and the honest wallet state", () => {
    const payload = testsPayload();
    render(<MemeTestsTotals totals={payload.totals} sources={payload.sources} />);
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("2 fechada(s) · 1 aberta(s)")).toBeInTheDocument();
    expect(screen.getByText("2 de 2")).toBeInTheDocument();
    expect(screen.getByText("+0.3600 SOL")).toBeInTheDocument();
    expect(screen.getByText("abertas à marca: +0.0500 SOL")).toBeInTheDocument();
    expect(screen.getByText("+US$ 65.16")).toBeInTheDocument();
    expect(screen.getByText("1.80 R")).toBeInTheDocument();
    expect(screen.getByText("sem carteira observada ainda")).toBeInTheDocument();
  });

  it("says how many closed bets have no US$ quote instead of pretending a total", () => {
    const payload = testsPayload({ totals: { ...testsPayload().totals, pnl_usd: null, unpriced_usd: 2 } });
    render(<MemeTestsTotals totals={payload.totals} sources={payload.sources} />);
    expect(screen.getByText("sem cotação")).toBeInTheDocument();
    expect(screen.getByText("2 fechada(s) sem cotação SOL/USD na saída")).toBeInTheDocument();
  });
});
