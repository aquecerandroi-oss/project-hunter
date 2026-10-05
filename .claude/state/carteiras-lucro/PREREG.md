# PREREG — rascunho do bloco da Fila (NÃO inserido; o orquestrador faz o merge)

> Escrito em 05/10/2026 pelo quant-engineer, **antes** de existir coletor, tabela ou qualquer dado da população
> inteira. Desenho: `docs/design/seguir-carteiras-lucrativas.md`. Revisão da Astra:
> `.claude/state/astra-review-carteiras-lucro-design.md` (os 9 itens obrigatórios foram absorvidos neste texto).
> Id **H-030** proposto como o próximo livre. A primeira escolha foi H-029, mas às 15:50Z a R87 (carry de funding) o
> tomou na Fila, e o rascunho H-028 da coorte prospectiva da H-026 também já existe. Por isso renumerei para H-030 antes
> de qualquer dado. O grep não achou H-030 em `obsidian/`, `.claude/state/` nem `docs/` às ~19:30Z. A nota de síntese
> virou **KB-0182**, porque a R87 reservou a KB-0181 para o resultado do carry. Se outro bloco pegar o número antes,
> renumerar sem mudar nada no conteúdo.
> **Congelamento:** este texto só vale como pré-registro depois de aprovado pelo Everton e copiado para a Fila com
> data e hora. Isso tem de acontecer antes de o coletor completar 7 dias, porque nenhum desfecho pode ter sido visto.

---

## H-030 — Seguir quem ganha dinheiro copiável (top-30 por C-PnL, 100 % de cobertura, replay causal para frente)

- **origem:** pedido do Everton (05/10/2026: "começamos a seguir quem faz dinheiro de verdade"). R57/[[KB-0136-carteiras-vencedoras-nao-sao-gatilho]]: vencedores persistem (ρ ≈ 0,6), mas o lucro é velocidade e pacote, e copiar 3 s depois dá 1,01× (R +0,03 contra −0,04 do controle, IC do Δ [−0,06; +0,21]). A fita cobria 5 % dos mints, com 26 s de atraso. [[KB-0142-kol-e-call-antecipam-ou-confirmam]] mostrou que o selo KOL chega no pico. Síntese: [[KB-0182-quem-ganha-dinheiro-de-verdade-nos-memes]]. Esta hipótese **não reabre** a R57 com outro nome. Ela traz **medida nova** (ranking por PnL copiável, simulado com o nosso atraso medido, em vez do PnL deles; entidade em vez de carteira; filtro de posse; saída espelhando a venda) **e população nova** (o programa inteiro, para frente, com cobertura por slot), que é o que a regra 1 da Fila exige para uma ideia voltar. **Família de tentativas "quem está comprando"** (todas fracassadas ou não confirmadas): R57 (seguir top-30), R61 (KOL), E2-b/EXP-M9 (pedigree, maior comprador), H-010 (concentração do maior comprador), H-014 (rede de financiamento), H-015 (bundle do slot da criação, REFUTA). Esta é a 7.ª; o leitor deve descontar por isso.
- **variável:** `followed(e, D)`, que diz se a entidade *e* está entre as 30 maiores por **C-PnL** no retrato do dia D. C-PnL é a soma, na janela de 7 dias até `T_D` = D 00:00 UTC, do resultado líquido da **mesma política de cópia** descrita abaixo, aplicada a cada compra-gatilho de *e*. Só entram cópias cujo desfecho completo terminou antes de `T_D`, com todos os eventos `received_at` < `T_D`. Para ser elegível, a entidade precisa ter, todos ao mesmo tempo:
  - **E-PnL ≥ +2 SOL**, onde E-PnL = W-PnL realizado mais a variação do valor de liquidação do inventário aberto entre o início e o fim da janela; a marcação na última cotação nunca entra;
  - ≥ 20 episódios não neutros, em ≥ 15 mints e em ≥ 4 de 7 dias;
  - dias com E-PnL > 0 ≥ 4/7;
  - queda máxima do E-PnL acumulado ≤ max(1 SOL; 50 % do E-PnL);
  - maior episódio ≤ 50 % do E-PnL;
  - tempo de posse mediano ≥ 60 s e fração com posse < 10 s ≤ 25 %;
  - C-PnL > 0;
  - `unmatched` ≤ 20 % dos tokens vendidos.

  **Exclusões do ranking**, todas só com dados anteriores ao corte:
  - episódio em mint criado pela entidade ou por quem a financiou (1 salto); se forem > 20 % dos episódios, a entidade sai;
  - compra até 2 slots depois do `create`; se forem > 30 % dos episódios, a entidade sai;
  - compra e venda a ≤ 2 slots uma da outra;
  - > 500 trades no dia anterior.

  **Entidades:** união por mesmo financiador não-exchange (forte) ou por mesmo slot em ≥ 3 mints (fraca), valendo do retrato seguinte ao `known_at`. **Política de cópia (braço `follow`):**
  - **gatilho:** primeira compra ≥ 0,1 SOL de uma seguida num mint, fora de 2 slots do `create` e fora de mint criado pela própria entidade, com `received_at` + 0,4 s ≤ o instante do slot de pouso; no máximo 20 por entidade por dia (as primeiras) e 1 por mint a cada 30 min;
  - **entrada:** slot + 5, com 0,05 SOL, pelo pior preço entre antes e depois de todos os trades do slot de pouso; sem trade no slot, vale o último estado com slot ≤ pouso, nunca o próximo trade;
  - **saída** (pousando 5 slots depois do disparo): o primeiro entre a entidade passar de 50 % vendido, a cotação de venda dos nossos tokens ≤ 50 % do custo, ou 60 min;
  - **custos:** bps do evento, mais 50 000 lamports por perna e 5 000 lamports pelo fechamento da ATA;
  - **R** = (múltiplo líquido − 1)/0,5.
- **população:** todas as apostas `follow` e `control` geradas pelo replay causal noturno **sobre eventos recebidos depois do congelamento**, do programa pump e da PumpSwap, decodificados pelo coletor `wallet-tape` (desenho §2), a partir do primeiro 00:00 UTC depois do congelamento **e** de 7 dias completos de feed coberto (aquecimento). Nada do aquecimento entra no veredito. Dias com cobertura do programa < 95 % dos slots ficam fora inteiros, com a lista publicada. **Controle 1 (H2):** para cada `follow`, uma compra de entidade **elegível fora do top-30** no mesmo minuto (±60 s), em outro mint, mesma praça, mesma faixa de idade (< 5 / 5–60 / > 60 min) e mesmo tercil de SOL real na curva antes do gatilho. O sorteio usa semente 20261005, sem reposição, desempate pelo hash da assinatura, e a mecânica é idêntica. **Controle 2:** entidade ativa não elegível, mesmo pareamento; é descritivo e não tem teste.
- **previsão:**
  - **H1:** R líquido médio do `follow` a 5 slots ≥ **+0,05** (efeito mínimo relevante), com limite inferior do IC 95 % > 0.
  - **H2:** Δ pareado (`follow` − Controle 1) ≥ **+0,05**, com limite inferior do IC 95 % > 0.
  - **Inferência:** média por regressão na constante, erro-padrão com cluster em duas vias, **dia × entidade** (Cameron, Gelbach & Miller 2011), e t com G − 1 graus de liberdade, G = min(dias, entidades). Robustez: bootstrap *pigeonhole* (dia × entidade, 10 000 réplicas, semente 20261005), que **também** tem de dar limite inferior > 0. p unilateral de cada uma, com **Holm sobre {H1, H2}** a 0,05.
  - **CONFIRMA** exige **todas** estas condições:
    - H1 e H2 passam;
    - a 13 slots, a média do `follow` é > 0;
    - sem o 1 % maior das apostas, a média é > 0;
    - sem a entidade de maior contribuição, a média é > 0;
    - apostas contaminadas (lacuna no intervalo) ≤ 2 %, e H1 se mantém com as contaminadas a R = −1;
    - censuradas (migração sem pool decodificável) ≤ 5 %, já entrando no primário a R = −1;
    - com só as ligações fortes, a média é > 0;
    - com rede a 100 000 lamports por perna, a média é > 0.
  - **Previsão honesta (registrada):** **NÃO CONFIRMA**. Ponto previsto para H1 ≈ −0,03 R e para H2 ≈ +0,02 R, porque a fresta da R57 era cauda e a mediana era negativa. **Potência declarada:** SD a priori de 1,2 R (R57; não medido aqui). Com independência, 2 000 apostas detectam ≈ 0,075 R e 4 500 detectam 0,05 R (α unilateral 0,025, 80 %). O cluster em duas vias piora as duas contas, e por isso NÃO CONFIRMA é o desfecho esperado mesmo se o efeito existir.
- **refutação:**
  - **REFUTA** o tamanho previsto quando o limite superior do IC 95 % de H1 fica < +0,05 R pelos **dois** métodos (CGM e *pigeonhole*). Se além disso ficar < 0, registra-se que seguir perde dinheiro.
  - **REFUTA H2** separadamente pela mesma regra.
  - **NÃO CONFIRMA:** qualquer outra combinação, inclusive faltar uma das condições conjuntas do CONFIRMA. Imprecisão nunca vira refutação (errata do R76).
  - **Limite de dado (NÃO CONFIRMA, sem julgar o efeito):** < 2 000 apostas `follow` no dia 28; < 14 dias válidos; < 30 entidades distintas com ≥ 10 apostas cada (as entidades com menos de 10 **continuam** no resultado e só contam contra esse piso); cobertura de pareamento de H2 < 60 %.
  - **Encerramento (fixo):** leitura **única**, no primeiro 00:00 UTC em que (≥ 4 500 apostas **e** ≥ 14 dias válidos) **ou** no dia 28, o que vier primeiro. Antes disso só se olha a saúde do instrumento: cobertura, contagem de apostas e de elegíveis, atraso do feed e taxa de lacuna. **R, acerto e PnL ficam sem leitura**, e quem os olhar invalida a coorte.
  - **Abortar (sem veredito):** cobertura < 95 % em > 3 dias; upgrade de programa que quebre decodificador por > 24 h (o relógio da coorte para); `received_at − block_time` p50 > 2 s num dia (dia fora); defeito no motor de replay. Abortar exige id novo e coorte nova em dado novo, **nunca** um reprocessamento com o conserto sobre a mesma coorte depois de ver desfecho.
  - **Portão de nascimento:** com < 30 entidades elegíveis no 7.º dia de aquecimento, a hipótese **não nasce**. Fica registrado assim, sem afrouxar limiar.
- **registro:** rascunho em 05/10/2026 ~19:00Z, antes de existir qualquer dado da população inteira. Dados consultados antes, todos fora de qualquer cálculo de desfecho:
  - contagens de `meme_trades`/`meme_tokens` por dia;
  - tamanho das tabelas;
  - a latência slot-gatilho → slot-pouso das 62 compras reais de 24–26/09 (p50 3,5, p75 5, p90 12,3 slots), que fixa o atraso de 5/13;
  - a fita de decisão mais recente (02/10 15:47Z).

  Nenhuma carteira foi ranqueada e nenhum C-PnL foi calculado.
- **status:** rascunho (aguarda aprovação do desenho e o deploy da T4.8e)

---

## Notas para quem fizer o merge

- O bloco mantém os seis campos obrigatórios (`origem`, `variável`, `população`, `previsão`, `refutação`, `status`) e acrescenta `registro`, como H-015 e H-028.
- Ligar na EXP-M15 como **linhagem** (o rascunho de 18/09 media "≥ 2 do top-30 em 60 s" com a saída da mesa). Esta é outra hipótese. A EXP-M15 continua como registro do desenho antigo, ou recebe uma seção "substituída por H-030" se o Everton aprovar.
- Mapa de Estratégias: a linha "Seguir carteira vencedora — nao_confirma" **não muda** até haver veredito.
