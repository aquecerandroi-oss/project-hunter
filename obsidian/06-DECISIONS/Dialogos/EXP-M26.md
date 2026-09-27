---
tags: [dialogo, meme, exp-m26, grafico, moedas-maduras]
updated: 2026-09-26
status: registro
owner: sexta-feira
decided_on: 2026-09-26
by: sexta-feira (claude+astra)
---

# Diálogo — EXP-M26 (gráfico em moedas maduras, 5 rodadas)

Cinco rodadas entre Claude e a Astra (papel `quant-engineer`) desenhando o EXP-M26 (retenção madura
15–120 min, três conjuntos `research_only`, tabela nova `meme_mature_opportunities`/R1) a partir do
desenho `docs/design/exp-m26-grafico-moedas-maduras.md`. As rodadas 1–4 terminaram em **REVISE**: os
bloqueios sucessivos foram o contraste/independência da observação (r1), isolamento do rastreador e
denominadores (r2), classificação de vendas sem praça executável e H-022 (r3), e por fim pedigree
desconhecido vs. exclusão substantiva + a regra exata de REFUTA com dois ICs (r4). A rodada 5 abriu com
**DECISÃO CONJUNTA**: convergência no desenho, sem MUST-FIX de desenho restante — seed e coleta
confirmatória continuam condicionados aos aceites de implementação de R1 e J.

## DECISÃO CONJUNTA (rodada 5, Astra)

> Convergimos no desenho do EXP-M26. Os dois MUST-FIX da rodada 4 estão resolvidos no protocolo; não
> encontrei outro bloqueio de desenho com cenário concreto. O acordo é sobre o que construir e provar:
> seed e coleta confirmatória continuam condicionados aos aceites abaixo.
>
> 1. População prospectiva de mints descobertos e retidos pela política madura, 15–120 min, três
>    conjuntos `research_only`, fórmula de linha v1, banda 0–0,25 e ticket 0,07 SOL preservados.
> 2. Primária associativa dentro de C, na primeira oportunidade desde o seed, registrada em R1 antes de
>    filtrar proposta, fill ou desfecho. Mint do piloto não volta para a inferência. L−C é descritivo;
>    H−L mede o pacote de saída sob observação conjunta L+C+H.
> 3. Exclusão substantiva conhecida separada de falha instrumental; denominadores elegíveis sem
>    diluição por exclusões, com todas as recusas preservadas.
> 4. Mesma população e estatística para D, IC, p, MRE e mínimos; dois ICs marginais por contraste,
>    família fixa de dois testes com Holm e regra de concordância pelos extremos dos ICs.
> 5. Instrumentação causal, orçamento das jovens preservado, acompanhamento das propostas/apostas e
>    censura pela praça efetiva da venda; estresse declarado como cenário condicional, sem promessa de
>    robustez geral.
> 6. J congelado e testado antes do seed; piloto técnico fora da inferência; parada pela guarda implica
>    NÃO CONFIRMA por instrumento. Não há evidência nova de vantagem nem decisão sobre dinheiro real.

**Sem novo MUST-FIX de desenho** — os dois da rodada 4 fecharam: pedigree desconhecido sem recusa
substantiva entra em I (E não dilui as taxas dos elegíveis); REFUTA exige `max(U_mint, U_blocos) < 0,03`
nos dois contrastes. Antes do seed continuam obrigatórios os aceites de R1 (durabilidade e primeira
oportunidade) e J (inferência executável, censura, sensibilidades/contabilidade, integração e
operação) — nenhum deles foi provado nesta rodada, só especificado.

Everton aprovou o desenho consensuado em 26/09 (H-022 registrada).

**Bruto:** `.claude/state/dialogue-EXP-M26.md`
**Relacionado:** [[EXP-M26-grafico-em-moedas-maduras|EXP-M26]] ·
[[06-DECISIONS/Revisoes-Astra/EXP-M26-design-R1|Revisão pontual R1 (Astra)]] ·
[[KB-0161-o-grafico-de-5-minutos-nao-existe-na-porta|KB-0161]] · [[KB-0149-o-que-a-mesa-real-ensinou|KB-0149]] ·
[[Fila de Hipoteses]] · `docs/design/exp-m26-grafico-moedas-maduras.md`
