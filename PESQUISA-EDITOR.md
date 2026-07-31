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

## Decisão tomada — B, e a razão inverteu o que este doc previa

**Implementado o editor de nota (B), não o corretor de régua (A).** No ar desde 2026-07-31.

A recomendação original deste doc (A primeiro, porque o erro típico é o sistema inteiro
deslocado) valia como hipótese e **não sobreviveu à medição**. Com o modo imagem
instrumentado, o **grau diatônico saiu 100% em toda condição testada** — a régua nunca
escorrega. O que sobra é pontual: ~2% de nome espúrio e ~1% de nota faltando. Erro pontual
pede ferramenta pontual.

### Como ficou

A prévia passou a vir **sem** os nomes, e os nomes viraram um **SVG por cima**, em unidades
de ponto da página — assim o overlay escala junto com a imagem sem nenhuma conta de zoom, e
cada nome é um alvo de clique de verdade.

- **tocar num nome** → campo inline: corrige, ou apaga se deixar vazio
- **tocar no vazio** → acrescenta um nome ali
- **o download é gerado no clique**, já com as edições (por isso é um botão, não um link)

### Duas peças novas no núcleo

- `escrever(..., desenhar=False)` devolve onde cada nome **ficou** (`x0`, `y`), inclusive a
  2ª fileira que ele cria quando dois nomes colidem. Sem isso o overlay mostraria uma coisa
  e o PDF escreveria outra.
- `estampar_bytes(dados, rotulos, ...)` é o caminho de volta: recebe a lista editada e só
  põe tinta, sem reler nada. `anotar_bytes(estampar=False)` é a ida.

### Armadilhas que apareceram na implementação

1. **Acento grave dentro do Python inline.** O `.py` que o site executa vive numa template
   string do JS; um `` ` `` num comentário Python **fecha a string** e o arquivo todo deixa
   de parsear. Custou um erro de sintaxe difícil de ler.
2. **`.corpo` é um grid.** Pôr o palco e a legenda como dois filhos criou duas *colunas* e a
   partitura encolheu para metade da largura. Precisa `grid-column: 1 / -1`.
3. **`currentColor` no overlay.** O fundo ali é a partitura branca, mas o tema escuro passa
   cinza-claro: os nomes ficavam ilegíveis. Preto fixo, que é o que o PDF estampa.
4. **Posicionar o campo pelo `<text>` não funciona para nome novo** — rótulo recém-criado
   tem texto vazio, então não existe elemento para medir. A posição sai da matriz do SVG
   (`getScreenCTM`), que serve nos dois casos.
5. **Revogar o blob URL no mesmo tick do `click()`** pode abortar o download antes de ele
   começar.

### Limites

- **Só a 1ª página é editável** (é a única com prévia). Num PDF de várias páginas as outras
  saem como foram lidas — os rótulos delas continuam na lista e são estampados.
- **Não move nem arrasta**: corrige, apaga, acrescenta. Mover ficou de fora.
- O corretor de régua (A) **não** foi implementado e provavelmente não precisa, enquanto o
  grau continuar em 100%.
