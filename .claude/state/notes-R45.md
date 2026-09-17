# R45: Audit de restarts — hunter-meme-worker-1 (18 reinícios, T4.47 não deployado)

## Resumo executivo

O container `hunter-meme-worker-1` acumulou **18 restarts entre 2026-09-16T19:17:25Z e 2026-09-17T00:13:07Z (UTC)**, todos causados por um único tipo de falha: `CharacterNotInRepertoireError: invalid byte sequence for encoding "UTF8": 0x00` (byte NUL em frame de identity).

**Status**: A correção está pronta no local (commit `d1b0b40d`, T4.47) mas NÃO foi deployada na VPS. VPS segue em `7a5bacc` (18 commits atrás).

---

## Classificação dos 18 restarts

| Restart | Hora (UTC) | Hora (BRT) | Crash anterior (UTC) | Blind time | Causa | Fix | Deployado |
|---------|-----------|----------|-------------------|----------|-------|-----|-----------|
| 1 | 00:07:06 | 21:07:06 | 00:07:02 | 4s | CharacterNotInRepertoireError: NUL em name | d1b0b40d (T4.47) | ❌ |
| 2 | 00:07:10 | 21:07:10 | 00:07:07 | 3s | CharacterNotInRepertoireError | d1b0b40d | ❌ |
| 3 | 00:07:15 | 21:07:15 | 00:07:12 | 3s | CharacterNotInRepertoireError | d1b0b40d | ❌ |
| 4 | 00:07:21 | 21:07:21 | 00:07:17 | 4s | CharacterNotInRepertoireError | d1b0b40d | ❌ |
| 5 | 00:07:28 | 21:07:28 | 00:07:23 | 5s | CharacterNotInRepertoireError | d1b0b40d | ❌ |
| 6 | 00:07:35 | 21:07:35 | 00:07:29 | 6s | CharacterNotInRepertoireError | d1b0b40d | ❌ |
| 7 | 00:07:46 | 21:07:46 | 00:07:37 | 9s | CharacterNotInRepertoireError | d1b0b40d | ❌ |
| 8 | 00:08:04 | 21:08:04 | 00:07:48 | 16s | CharacterNotInRepertoireError | d1b0b40d | ❌ |
| 9 | 00:08:34 | 21:08:34 | 00:08:05 | 29s | CharacterNotInRepertoireError | d1b0b40d | ❌ |
| 10 | 00:11:42 | 21:11:42 | 00:11:39 | 3s | CharacterNotInRepertoireError | d1b0b40d | ❌ |
| 11 | 00:11:46 | 21:11:46 | 00:11:43 | 3s | CharacterNotInRepertoireError | d1b0b40d | ❌ |
| 12 | 00:11:51 | 21:11:51 | 00:11:48 | 3s | CharacterNotInRepertoireError | d1b0b40d | ❌ |
| 13 | 00:11:57 | 21:11:57 | 00:11:53 | 4s | CharacterNotInRepertoireError | d1b0b40d | ❌ |
| 14 | 00:12:03 | 21:12:03 | 00:11:58 | 5s | CharacterNotInRepertoireError | d1b0b40d | ❌ |
| 15 | 00:12:11 | 21:12:11 | 00:12:05 | 6s | CharacterNotInRepertoireError | d1b0b40d | ❌ |
| 16 | 00:12:22 | 21:12:22 | 00:12:12 | 10s | CharacterNotInRepertoireError | d1b0b40d | ❌ |
| 17 | 00:12:40 | 21:12:40 | 00:12:24 | 16s | CharacterNotInRepertoireError | d1b0b40d | ❌ |
| 18 | 00:13:10 | 21:13:10 | 00:12:41 | 29s | CharacterNotInRepertoireError | d1b0b40d | ❌ |

---

## Análise: blind time total e padrão

**Tempo total de indisponibilidade (soma dos blind times)**: 4+3+3+4+5+6+9+16+29+3+3+3+4+5+6+10+16+29 = **168 segundos** (2 min 48 s)

**Padrão observado**: O blind time cresce ao longo do intervalo, passando de ~3–4 s nos primeiros ciclos para ~16–29 s nos últimos. Isso sugere que o crash está ocorrendo repetidamente e causando retries do mesmo frame problemático no laço.

---

## Causa única: CharacterNotInRepertoireError (NUL byte)

**O que aconteceu**: Um frame de create do pump.fun chegou com um byte NUL (`\x00`) embutido no campo `name`: `"spaceX链游\x00"` (às 00:07:02 UTC = 21:07:02 BRT em 17/09).

**Impacto**: PostgreSQL rejeita `text` com `\x00` (CharacterNotInRepertoireError). A stream tentou reenviar o mesmo frame 6 vezes em 53 segundos, e cada tentativa derrotou o TaskGroup inteiro do worker, forçando restart.

**Sintoma no log**:
```
asyncpg.exceptions.CharacterNotInRepertoireError: invalid byte sequence for encoding "UTF8": 0x00
  sqlalchemy.dialects.postgresql.asyncpg.Error: <class '...CharacterNotInRepertoireError'>: ...
  sqlalchemy.exc.DBAPIError: (...) <class '...CharacterNotInRepertoireError'>: ...
ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)
```

---

## Fix implementado (não deployado)

**Commit**: `d1b0b40d` — "fix(meme-worker): T4.47 — strip NUL bytes from token rows at construction"

**Arquivos modificados**:
- `services/meme-worker/hunter_meme_worker/repo_rows.py` (+34 linhas)
- `services/meme-worker/tests/test_repo_rows_nul.py` (+62 linhas)

**O que faz**: 
1. `TokenRow.__post_init__()` passa por todos os 6 campos `str` no dataclass
2. Para cada campo, chama `clean_text(value)` que remove o byte `\x00`
3. Se a string ficava apenas com NULs, vira `None` ("não observado", mesmo que `discovery._identity` para campo vazio)
4. Campos obrigatórios (`mint`, `first_seen_source`) que viram `None` são mantidos como `""` para o schema rejeitar loudly em vez de silenciosamente inserir NULL

**Cobertura**: 6 produtores de TokenRow — discovery, boards, curve_rows, mayhem, risk, repo.

---

## Status de deployment

| Ponto | Status |
|-------|--------|
| **Commit da VPS atual** | `7a5bacc` ("plantao(meme): tendências 16/09 17h") |
| **Commit com fix** | `d1b0b40d` (T4.47, criado em 2026-09-16T22:20:06−03:00) |
| **Distância** | 18 commits atrás na VPS |
| **Ordem de ascendentes** | 7a5bacc é ancestor de d1b0b40d ✓ (fix está em frente) |
| **Deploy realizado?** | ❌ NÃO — fix compilado e testado localmente, VPS ainda rodando versão antiga |

---

## Outras causas investigadas

### "meme_pedigree_read_failed" warnings
- Aparecem no log a cada ~1h (20:17 UTC, 21:17 UTC, 22:17 UTC, 23:17 UTC, etc.)
- **Nível**: `warning`, não fatal
- **Impacto**: Nenhum restart associado
- **Causa**: Leitura de pedigree falhou (problema externo, não code crash)
- **Status**: Esperado e tolerado pelo sistema

### Outras exceções
- ❌ Nenhuma outra encontrada nos logs

---

## Respostas rápidas

**P: Por quanto tempo o worker fica indisponível após cada crash?**
- De 3 a 29 segundos. Média ~9 s. O padrão de crescimento sugere que a chegada do frame problemático está sendo retentada pela stream, e cada retry toma mais tempo (provável backoff ou degradação do estado interno).

**P: Há mais de uma causa?**
- Não. Todos os 18 restarts apontam para o mesmo byte NUL no campo `name` de um frame.

**P: O fix deve ser deployado?**
- Sim, imediatamente. O código está pronto, testado (`test_repo_rows_nul.py` com 5 cenários) e resolve o único problema.

**P: Qual arquivo mudar e por quê?**
- `services/meme-worker/hunter_meme_worker/repo_rows.py`: A lógica do `clean_text()` e `TokenRow.__post_init__()` está aí. O deploy do commit d1b0b40d já traz a solução completa. Nada adicional a mudar.

---

## Conclusão

**Diagnóstico**: 18 restarts = 1 causa (NUL byte no nome de moeda Solana), 168 s cego, fix pronto mas não na VPS.

**Ação**: Fazer deploy de d1b0b40d e posteriores na VPS (compose.sh update).
