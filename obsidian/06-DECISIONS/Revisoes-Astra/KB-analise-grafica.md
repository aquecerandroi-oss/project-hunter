---
tags: [astra, revisao, cripto, meme, analise-tecnica, pesquisa]
date: 2026-09-28
updated: 2026-09-28
status: fechada
owner: sexta-feira
decided_on: 2026-09-28
by: Astra + quant-engineer
---

# Revisão da Astra — análise gráfica: o que sobra depois do custo (KB-0167, 28/09/2026)

**Tarefa:** leitura da literatura aberta sobre análise técnica/gráfica (Brock et al.; Sullivan, Timmermann & White;
Lo, Mamaysky & Wang; Park & Irwin; Hudson & Urquhart; Corbet et al.; Grobys et al.; Gerritsen et al.; Shen et al.;
Osler) e ranking de candidatas para depois do EXP-M26, sem consultar preço nem desfecho nosso
([[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]]).

**Conferência:** ela refez os números contra os textos extraídos (`.claude/state/kb167-fontes/`) e não achou erro
de transcrição.

**Aceitos os 5 must-fix:** (1) resumo e ranking generalizavam além dos estudos — osciladores resistem a custo em
Hudson & Urquhart, o resumo de Schulmeister não mostra queda clara no intradiário, e dois testes de volume não
esgotam "confirmação por volume"; (2) "líquido de custo" misturava custo de equilíbrio intradiário, regra diária e
resultado sem custo — virou tabela por estado da evidência, e as tabelas 6 e 8 não mostram a interseção custo ×
correção; (3) Corbet et al. com e sem banda (+0,0138 % × −0,2627 %) — o apoio a C2 ficou fraco e indireto; (4) o
contexto do Lab é por versão (piso 1.560, teto 6.000 min), a retenção de 90 d não prova cobertura, e a
`volume_anomaly` decide em 5 min; (5) C3 virou extrapolação explícita, com visitas distintas separadas de
aproximação prolongada.

**Ranking das candidatas:** concorda com C1 → C2 → C3 como prioridade provisória, nenhuma registrada. C1 só com teste
incremental contra a pista `_low`, ATR% e `return_4h`, por estratégia, em coorte futura; C2 herda as guardas da
H-022 e fica bloqueada se ela fechar por instrumento; C3 por último. **Recomendação registrada, fora do escopo da
leitura:** rever a prontidão da `sweep_reclaim_v1` ([[EXP-0017-sweep-reclaim]]) antes de desenvolver C3; atualizar
[[Dicionario de Variaveis]] e a EXP-0017 fica com o orquestrador. **Divergência:** nenhuma de conteúdo.

Bruto: `.claude/state/astra-review-KB-analise-grafica.md`. Relacionado: [[Proximas Hipoteses]] ·
[[06-DECISIONS/Revisoes-Astra/Index|Revisões da Astra]]
