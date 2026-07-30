# Módulo de correção de erro de transcrição

Estudo de viabilidade — 2026-07-29. Pergunta original: dar ao programa uma forma de
**corrigir o PDF quando a transcrição erra**.

## Veredito

Viável e barato. Mas **o editor óbvio — clicar na nota e trocar a letra — é o que resolve
menos**, porque erro de transcrição aqui quase nunca é uma nota solta.

A transcrição é uma **régua encostada na pauta**: apoia nas 5 linhas e mede a altura de
cada cabeça. Quando erra, geralmente não foi uma medida torta — foi a **régua que
escorregou**. E régua escorregada não se conserta apagando as 40 medidas uma por uma; se
conserta reposicionando a régua e medindo de novo.

## Anatomia dos erros

| Causa | Estrago |
|---|---|
| pauta detectada uma linha acima/abaixo | **todo o sistema** sai 2 graus errado |
| armadura lida errada | **todos** os F viram F#, etc. |
| `topo_ref` da clave errado | sistema inteiro deslocado |
| cabeça isolada lida errado | 1 nota — é o resto dos 99,51% |

Com 99,51% de acurácia, um arquivo de 200 notas tem ~1 erro solto. Vários erros juntos =
era a régua, não a medida.

## O encaixe é limpo — zero mudança de núcleo

A separação necessária **já existe** no código, só não está exposta:

- `ler_notas(pg, sistema)` → devolve os rótulos
- `escrever(pg, rotulos, cor)` → estampa
- `anotar_bytes()` faz as duas numa tacada

Cortar no meio (devolver os rótulos como JSON → usuário mexe → chamar `escrever()` no fim)
é **só UI**. O núcleo não muda.

Mapear clique → rótulo também é trivial: cada rótulo já tem `x` e `y_base` em pontos PDF, e
a prévia é `get_pixmap(dpi=96)`, então `pixel = ponto × 96/72`. O custo real é outro: hoje
a prévia é **PNG estático da primeira página só** (`index.html`, `_previa`); editor exige
renderizar todas as páginas, e aí memória e tempo crescem.

## Três níveis

| | O que faz | Custo | Conserta |
|---|---|---|---|
| **A. Corretor de régua** | por sistema: "sobe/desce 1 linha", "forçar armadura = 2 bemóis" → re-roda a leitura | **baixo** — parâmetros de override em `ler_notas`, poucos controles na UI | o erro típico: dezenas de notas por clique |
| **B. Editor de nota** | clica no rótulo, digita o certo | médio — prévia interativa de todas as páginas | o erro raro: 1 nota por clique |
| **C. Editor completo** | mover, apagar, adicionar rótulo, arrastar | alto — vira app de edição, outro produto | tudo |

**A primeiro.** Sozinho resolve a maior parte. **B** é o que se pede primeiro e entrega
menos. **C** está fora do escopo do projeto (a ferramenta estampa uma camada de texto; não
é editor de partitura).

## Por que isso ficou mais importante

No **modo screenshot** ([[PESQUISA-SCREENSHOT.md]]) a acurácia cai em relação ao modo
vetor. Ali o corretor deixa de ser conveniência e passa a ser o que torna o modo usável.

## Decisão pendente

**Escolher entre A e B depende de qual erro aparece na prática nos PDFs do Manuel: nota
solta ou trecho inteiro deslocado?** Sem esse dado concreto, a escolha seria por
estatística de acervo, não por experiência de uso. Responder isso antes de implementar.
