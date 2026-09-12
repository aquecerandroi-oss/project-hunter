**RESUMO**
Como `quant-engineer`, testaria **diagnóstico do item 1 → M-P18v2 → M-P24**, entre essas três opções. O primeiro valida o desfecho usado pelas outras; M-P18v2 já tem protocolo mais definido; M-P24 ainda mistura duração de exposição, identidade das carteiras e disponibilidade dos dados.
A conclusão sustentada é **“complete REST não basta para comprovar migração”**. A divergência entre duas listas incompletas não demonstra sozinha a semântica de nenhuma delas.

**ARQUIVOS**
Nenhum criado ou modificado; nenhum commit.

**TESTES**
Conferência local com PowerShell (`Get-Content`, `ConvertFrom-Json`, cruzamento por mint): **140 únicas, 77 com reserva SOL zero, 68 presentes no board; 43 mints repetidos entre runs 3/5, sendo 42 pump**. Suites não executadas: revisão documental.

**MUST-FIX**

1. **Separar conclusão da curva, migração e primeira observação.** O [rascunho:93](/C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0547-lane1.md:93) propõe `real_token_reserves=0 AND pool`, ou `gd`: isso funde eventos e aceita um substituto ainda não validado. Auditar estados/eventos por programa, assinatura, slot e pool canônico; manter os quatro indicadores separados. **Falha:** curva encerrada aguardando migração vira “não concluída”; pool alheio vira migração.

2. **Reserva zero e ausência no board não classificam fracasso.** Os 31 zeros entre os 68 comuns já invalidam esse atalho; esvaziamento para migração continua explicação possível, não comprovada. Os 72 ausentes são “não encontrados neste recorte”; os 68 presentes são “reportados pelo indexer”. **Falha:** excluir migrações verdadeiras ou declarar fracasso de Mayhem por cobertura seletiva.

3. **Retirar “replicação independente, três horas depois”.** Pelos `serverTs` dos brutos, runs 3/5 estão separados por **73,50 minutos**, com **42/49 pump anteriores reaparecendo**; três horas referem-se aproximadamente ao run 1. O [rascunho:99](/C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0547-lane1.md:99) contradiz isso. Deduplicar e avaliar uma janela futura; `|Δ|≤1 s` permanece proximidade temporal, não slot comprovado. **Falha:** contar as mesmas moedas como confirmação adicional e inflar a precisão.

4. **M-P24: congelar a lista realmente antes da exposição.** Arquivar endereços, regra de seleção, janela do ranking, versão e recepção; `/pnl-leaderboard` seleciona vencedores passados, não comprova influência social. Para moedas criadas antes da janela de graduação, exigir lista anterior à criação ou redefinir prospectivamente a exposição. **Falha:** carteira entra no ranking graças à própria moeda analisada. Sem snapshot anterior preservado, esta rodada só gera hipótese.

5. **`gd` retrospectivo não prova disponibilidade na graduação.** Pode ancorar uma associação histórica após validação; para testar sinal utilizável, definir `decision_at` quando graduação, compras e classificação estavam disponíveis, contando outcomes posteriores. **Falha:** `gd=05:00`, recebido às 05:10, permite “prever” compradores das 05:00–05:10. Ordenar compras e migração por transação/instrução, inclusive dentro do mesmo slot.

6. **Controlar oportunidade de encontrar KOL e congelar os outcomes.** Comparar KOL presente/ausente dentro das células de duração, com atividade anterior, liquidez, programa e horário; registrar falta de cobertura como desconhecida. Fixar preço inicial do pool, retenção em +24 h e primeira compra por endereço em (graduação, +1 h], com histórico desde criação. **Falha:** moedas lentas acumulam mais compradores/KOLs e parecem melhores apenas por essa diferença; excluir pools desaparecidos melhora artificialmente a retenção.

**NICE-TO-HAVE**
Os **933× ATH/mc** são razão entre campos reportados: não demonstram trajetória negociável, retorno ou fraude. `kol` atual é contador opaco, inadequado para reconstruir compradores anteriores.
“**Compatível com janela deslizante**” está correto; “rola como esperado” exigiria reconciliar entradas, saídas e revisões. Duas amostras de poucos minutos tampouco demonstram mudança sustentada do ritmo.

**O QUE EU FARIA DIFERENTE**
Começaria pela matriz de concordância dos quatro indicadores em uma coorte prospectiva de criações, incluindo ausentes dos boards; depois aplicaria M-P18v2. M-P24 ficaria exploratória até cumprir os itens 4–6.

**CONCORDO COM**
Lista congelada supera `kol` posterior; população condicional às migradas é legítima para retenção, desde que não seja generalizada a todas as criações nem interpretada como efeito causal de KOL.

**OBSIDIAN**

- **Plantão MEME — 2026-09-12:** registrar run 5 com sobreposição, intervalo corrigido e limites das inferências.
- **Hipóteses do plantão:** detalhar M-D2 e pré-registrar M-P24 com lista anterior à exposição, disponibilidade, controles e outcomes.