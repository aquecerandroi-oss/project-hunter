// Assistente operacional — respostas por REGRAS sobre os registros (demonstrativo; sem modelo de IA conectado).
export function answer({ q, org, pf, D }) {
  const t = q.toLowerCase();
  const refs = [];
  const rejected = org.opps.filter((o) => o.riskLog && o.riskLog.result === "rejeitado").sort((a, b) => b.riskLog.at.localeCompare(a.riskLog.at));
  if (t.includes("rejeit")) {
    const m = t.match(/op-\d+/);
    const o = m ? org.opps.find((x) => x.id.toLowerCase() === m[0]) : rejected[0];
    if (!o || !o.riskLog) return { text: "Não encontrei registro de rejeição do Risk Engine para essa oportunidade nesta organização.", refs };
    refs.push(o.id);
    const failed = o.riskLog.checks.filter((c) => !c.ok).map((c) => `• ${c.name}: ${c.value} (limite ${c.limit})`).join("\n");
    return { text: `${o.id} (${o.sym}) foi rejeitada pelo Risk Engine em ${D.fmtDT(o.riskLog.at)}.\nCritérios que falharam:\n${failed}\n\nMotivo registrado: ${o.riskLog.reason}\nEstado atual: ${D.STAGE_LABEL[o.stage]}.`, refs };
  }
  if (t.includes("agente") && (t.includes("sem dado") || t.includes("paus") || t.includes("falh"))) {
    const bad = D.AGENTS.filter((a) => a.state === "pausado" || !a.dataOk);
    bad.forEach((a) => refs.push(a.id));
    return { text: bad.length ? `Agentes com problema de dados:\n${bad.map((a) => `• ${a.name} — ${a.state}${a.last ? `, última atividade ${D.fmtAgo(a.last)}` : ""}. ${a.desc}`).join("\n")}\n\nAgentes conectados: ${D.AGENTS.filter((a) => a.state === "conectado").map((a) => a.name).join(", ")}. Simulados: ${D.AGENTS.filter((a) => a.state === "simulado").map((a) => a.name).join(", ")}.` : "Todos os agentes conectados têm dados.", refs };
  }
  if (t.includes("exposi") || t.includes("carteira")) {
    const coins = pf.byCoin.map((c) => `• ${c.sym}: ${D.fmtPct(c.pct * 100)} (limite 10%)`).join("\n") || "• nenhuma posição aberta";
    org.positions.forEach((p) => refs.push(p.opp));
    return { text: `Exposição total: ${D.fmtPct(pf.exposure * 100)} do patrimônio (limite 40%).\nPor ativo:\n${coins}\n\nRisco planejado agregado: ${D.fmtPct(pf.riskAgg * 100, 2)} (limite 1%). Posições: ${pf.positionsCount} de 5.\nPatrimônio ${D.fmtUSDT(pf.equity)}; alocado ${D.fmtUSDT(pf.allocated)}; disponível ${D.fmtUSDT(pf.cash)}.\nKill switch: ${org.killSwitch}${org.paused ? " · pausa operacional ativa" : ""}.`, refs };
  }
  if (t.includes("mudou") || t.includes("última sessão") || t.includes("ultima sessao")) {
    const ev = org.events.slice(0, 5);
    ev.forEach((e) => e.ref && refs.push(e.ref));
    return { text: `Últimos registros desta organização:\n${ev.map((e) => `• ${D.fmtTime(e.at)} — ${e.text}`).join("\n")}\n\nNão há registro de ordens reais: este ambiente é paper.`, refs };
  }
  if (t.includes("experiment") || t.includes("revis")) {
    const need = org.experiments.filter((x) => x.verdict === "insuficiente" || x.verdict === "inconclusivo" || x.status === "rascunho");
    need.forEach((x) => refs.push(x.id));
    return { text: need.length ? `Experimentos que pedem revisão:\n${need.map((x) => `• ${x.id} — ${x.verdict || x.status}: ${x.limits || "sem resultado ainda"}`).join("\n")}` : "Nenhum experimento pendente de revisão.", refs };
  }
  if (t.includes("posi") || t.includes("aberta")) {
    org.positions.forEach((p) => refs.push(p.opp));
    return { text: pf.posRows.length ? pf.posRows.map((p) => `• ${p.sym}: ${D.fmtNum(p.qty, 4)} a ${D.fmtPrice(p.entry)}, agora ${D.fmtPrice(p.price)} → ${D.fmtSigned(p.unreal)} USDT (${D.fmtPct(p.unrealPct)}), stop ${D.fmtPrice(p.stop)}`).join("\n") : "Nenhuma posição aberta.", refs };
  }
  if (t.includes("kill") || t.includes("pausa")) return { text: `Kill switch: ${org.killSwitch}. Pausa operacional: ${org.paused ? "ativa" : "inativa"}. Acionar o kill switch bloqueia novas entradas e registra o evento; não encerra posições — o encerramento é uma ação separada, com execução correspondente.`, refs };
  return { text: "Consigo responder, com base nos registros desta organização, sobre: rejeições do Risk Engine, agentes sem dados, exposição da carteira, posições abertas, o que mudou recentemente e experimentos pendentes. Não invento operações nem altero limites de risco.", refs };
}
