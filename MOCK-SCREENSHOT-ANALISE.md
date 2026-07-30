# Mock de leitura por SCREENSHOT — análise detalhada

Experimento de 2026-07-29. Protótipo: `~/notes-pdf/_exploracao/mock_bitmap.py`.
Resumo executivo em [[PESQUISA-SCREENSHOT.md]]; aqui fica o detalhe para explorar depois.

---

## 1. Hipótese sob teste

> O núcleo não precisa de vetor. Precisa de duas estruturas — `horiz` (linhas da pauta) e
> `caminhos` (manchas com bbox e "tem buraco") — e o modo contorno faz o resto.

Se verdadeira, um modo bitmap é **um produtor de dados novo**, não um pipeline novo.

**Resultado: hipótese confirmada.** `pautas()` e `glifos_de_contorno()` consumiram dados
de pixel sem nenhuma alteração. A aritmética de altura acertou **100% em toda condição
testada**.

---

## 2. Metodologia

### 2.1 Screenshot sintético

`get_pixmap(matrix=Matrix(zoom, zoom), colorspace=csRGB)` sobre o PDF real, opcionalmente
re-encodado em JPEG para simular artefato de compressão. `zoom=1.97` corresponde a um A4
ocupando 1173 px de largura — a largura útil de um iPhone moderno em tela cheia.

### 2.2 O gabarito é o próprio PDF

O mesmo arquivo é lido por `ler_notas()` no modo vetor (acurácia conhecida de 99,51%) e o
resultado é convertido de pontos para pixels multiplicando por `zoom`. Qualquer divergência
é erro do bitmap. **É um gabarito gratuito e em escala** — todo o acervo pode virar
conjunto de teste sem rotular nada à mão.

### 2.3 Injeção sem tocar no núcleo

`ler_notas()` só usa da página: `coletar(pg, com_ritmo=True)`, `pg.rect.width/height` e
`pg.rect.y1`. Então o mock faz monkeypatch de `A.coletar` e passa uma `PagFalsa` com o
`rect` da imagem. Contrato devolvido:

| campo | conteúdo no bitmap |
|---|---|
| `glifos` | `[]` — vazio de propósito, é o que dispara o modo contorno |
| `textos` | `[]` — não há span de texto numa imagem |
| `horiz` | `(y, x0, x1)` do maior run de tinta de cada fileira densa |
| `vert` | componentes verticais estreitos e altos (haste, barra) |
| `formas` | bbox de todos os blobs (só alimenta o cálculo do piso do rótulo) |
| `caminhos` | cabeças detectadas + blobs de contorno, com `curvas` simulando vazado |
| `beams` | `[]` — ritmo fora do escopo do mock |

### 2.4 Métricas

Par = cabeça do bitmap a menos de `0,7` espaço em x **e** em y da cabeça do gabarito,
casamento 1:1 (guloso pela menor distância).

| métrica | definição |
|---|---|
| **cabeças** | pares / notas do gabarito (recall de detecção) |
| **grau** | entre os pares, fração com `idx` (índice diatônico) igual — a letra |
| **nome** | entre os pares, fração com `nome` igual — letra **+** alteração |
| **FP** | rótulos do bitmap sem par no gabarito |

`grau` isola a aritmética de altura; `nome` mede também armadura e acidente.

---

## 3. Pipeline implementado

```
imagem RGB
  → grayscale + Otsu invertido                       (tinta = 1)
  → achar_horiz: projeção horizontal                 → horiz
  → pautas(horiz, W, H)                              → sistemas, esp
  → limpar: apaga linha de pauta                     → limpo
  → preencher_buracos(limpo, 0,85·esp²)              → cheio
  → cabecas_por_template(cheio, esp)                 → cabeças
  → blobs(limpo)                                     → clave, acidente, ponto
  → coletar_falso → ler_notas → rótulos
```

### 3.1 `achar_horiz` — linhas da pauta

Fileira candidata: soma de tinta ≥ `0,18·W`. Dela sai o **maior run** de tinta tolerando
buracos de ≤ 4 px (a linha é cortada pelas hastes), e só entra se cobrir ≥ 15% da largura.
A espessura da linha vem da mediana dos runs verticais de fileiras consecutivas.

Devolve **um segmento por fileira**, não vários — importante: `pautas()` mede a **união**
dos segmentos (`_cobertura`), então passar vários pedaços curtos reintroduziria a linha
fantasma da armadilha nº 3 do `CLAUDE.md`.

### 3.2 `limpar` — remoção de linha de pauta

Pixel é apagado se: está numa fileira de pauta **e** não pertence a nenhum traço vertical
mais alto que `2,5·espessura_da_linha`. A segunda condição é o que preserva o que
atravessa a linha (cabeça, haste, barra). Depois, `close` vertical de `espessura + 2` px
para religar o que a remoção cortou.

### 3.3 `preencher_buracos` — só buraco pequeno

Componentes do **fundo** que não tocam a borda da imagem e têm área ≤ `0,85·esp²` são
tapados. Serve para a mínima/semibreve sobreviver ao detector.

### 3.4 `cabecas_por_template` — correlação

Template: elipse preenchida de `1,30 × 1,06` espaço, inclinada 20°.
`matchTemplate(TM_CCOEFF_NORMED)`, máximo local numa janela de `0,9·esp`, e três cortes:

| corte | valor testado | o que rejeita |
|---|---|---|
| correlação | 0,45–0,75 | mancha de forma errada |
| preenchimento da elipse | ≥ 0,80 | letra "o", pausa (anel ou zigzag) |
| alinhamento a meio-espaço | ≤ 0,18 espaço | mancha em posição diatônica impossível |

`vazia` = o pixel do centro estava branco **antes** de tapar buraco.

O bbox devolvido é **sintético** (centro ± dimensões nominais), não o bbox da mancha. Foi
uma decisão: o bbox medido é contaminado pelo `close` e por cabeças que se tocam.

---

## 4. Resultados, iteração por iteração

O log completo importa mais que o número final: cada regressão isolou uma armadilha.

### Iteração 1 — componentes conexos, `close` de `3·esp_linha+1`

| PDF | cabeças | grau | nome | FP |
|---|---|---|---|---|
| Marlon Blanco p0 | 75,6% (118/156) | 98,3% | 98,3% | 8 |

Diagnóstico das 38 perdas, medindo o blob que cobre o ponto da cabeça:

| causa | n | evidência |
|---|---|---|
| blob grudado | 20 | `w=2,97` e `w=4,21` espaços — 2 e 3 cabeças num só componente |
| altura fora da faixa | 16 | `h=1,44` contra faixa `0,80–1,35`; `w=1,33` estava perfeito |
| largura fora | 2 | `w=1,95` — duas cabeças lado a lado |

→ **16 eram bug meu**: o `close` de 4 px inflava uma cabeça de ~10 px em 40%.
→ **22 eram limitação real do componente conexo**: cabeças vizinhas de um grupo com beam
se tocam nos cantos.

### Iteração 2 — núcleo por erosão elíptica, `close` de `esp_linha+2`

| PDF | cabeças | grau | nome | FP |
|---|---|---|---|---|
| Marlon Blanco p0 | **100%** (156/156) | **100%** | 100% | 43 |

Recall resolvido, FP apareceu. Diagnóstico dos 43, contra os glifos do vetor:

| causa | n |
|---|---|
| texto impresso ("Do", "=", "90") | 14 |
| longe de qualquer glifo (1,4–4,9 esp) — pausas | ~26 |
| clave | 3 |

**Nota de método:** a primeira tentativa de diagnóstico classificou 26 FP como
"em cima de uma cabeça", o que era falso. Causa: o bbox de glifo do PyMuPDF tem altura de
**linha de texto**, não de tinta (armadilha nº 2 do `CLAUDE.md`), então tudo "cai dentro"
da caixa de uma cabeça. Refeito com o centro corrigido `g["y"]`.
As pausas não apareceram como glifo porque `coletar()` sem `com_ritmo` não as inclui.

### Iteração 3 — correlação com template, varredura de limiar (zoom 1,97)

| PDF | 0,40 | 0,50 | 0,60 | 0,70 |
|---|---|---|---|---|
| Marlon (cabeças / FP) | 100% / 489 | 100% / 233 | 100% / 75 | 98,1% / 20 |
| Song_of_somg | 95,4% / 276 | 92,0% / 100 | 92,0% / 31 | 90,8% / 17 |
| Paso Corto | 100% / 429 | 100% / 242 | 100% / 67 | 100% / 29 |
| cadernin p0 | falhou: nenhuma pauta detectada | | | |

Grau = 100% em todas as células. **Mas `nome` despencou**: 22,9% no Song_of_somg, 56% no
Paso Corto. A alteração estava sendo perdida.

### Iteração 4 — a haste (limiar 0,70)

| config | Marlon | Song_of_somg | Paso Corto |
|---|---|---|---|
| remove haste | 98,1% / grau 100% / **nome 100%** / FP 20 | 90,8% / 100% / **nome 22,8%** / FP 17 | 100% / 100% / **nome 56,0%** / FP 29 |
| preserva haste | 77,6% / 100% / **nome 97,5%** / FP 10 | 81,6% / 100% / **nome 98,6%** / FP 16 | 81,1% / 100% / **nome 100%** / FP 5 |

**Armadilha:** o sustenido é feito de dois traços verticais compridos e estreitos —
indistinguível de haste por geometria. Removê-los apaga a armadura, e todo nome sai sem
alteração. O Marlon não sofreu porque está em tom sem acidentes na armadura.

Mas preservar a haste derrubou o recall — pela **segunda** armadilha: com haste, o
flood-fill preenche a área fechada por haste + beam + cabeça vizinha, criando uma mancha
sólida enorme onde a correlação com elipse desaba.

### Iteração 5 — buraco pequeno (≤ 0,85 esp²) + haste preservada

| limiar | Marlon | Song_of_somg | Paso Corto |
|---|---|---|---|
| 0,55 | 100% / 100% / 100% / FP 150 | 90,8% / 100% / 58,2% / FP 51 | 100% / 100% / 57,9% / FP 91 |
| 0,65 | 98,1% / 100% / 98,0% / FP 35 | 83,9% / 100% / 61,6% / FP 25 | 97,3% / 100% / 100% / FP 30 |
| 0,75 | 80,8% / 100% / 96,0% / FP 1 | 79,3% / 100% / 98,6% / FP 14 | 89,6% / 100% / 100% / FP 2 |

*(ordem: cabeças / grau / nome / FP)*

**O `nome` correlaciona negativamente com o FP**, não com o recall — ver §5.2.

### Iteração 6 — discriminantes extras (limiar 0,55, FP por PDF)

| config | Marlon | Song | Paso | efeito no recall |
|---|---|---|---|---|
| só correlação | 150 | 51 | 91 | — |
| + preenchimento ≥ 0,80 | 72 | 27 | 63 | Song 90,8% → 83,9% |
| + alinhamento ≤ 0,18 | 110 | 41 | 72 | Paso 100% → 99,6% |
| ambos | **54** | **26** | **49** | soma dos dois |
| ambos, limiar 0,45 | 121 | 35 | 53 | recall não sobe |

Os dois cortes juntos reduzem o FP a ~1/3 e **param aí**.

---

## 5. Análise

### 5.1 Piso de resolução

Config: correlação 0,65 + os dois cortes. Marlon Blanco p0.

| zoom | espaço | pautas achadas | cabeças | grau | FP | + JPEG q60 |
|---|---|---|---|---|---|---|
| 1,20 | 6,0 px | **5** (de 7) | **43,6%** | 100% | 47 | 45,5% / FP 21 |
| 1,97 | 9,8 px | 7 | 98,1% | 100% | 14 | **80,1%** / FP 16 |
| 3,00 | 14,8 px | 7 | 97,4% | 100% | 16 | 98,1% / FP 17 |

Duas leituras:

1. **O espaço de pauta em pixels é a variável de controle, não o tamanho do arquivo.**
   Abaixo de ~8 px por espaço, tanto a detecção de pauta quanto a de cabeça degradam.
   Alvo prático: **≥ 10 px por espaço** → A4 inteiro com largura ≥ ~1100 px.
2. **JPEG só machuca perto do piso.** Em 14,8 px é inócuo (97,4% → 98,1%); em 9,8 px
   custa 18 pontos de recall. Isso sugere um aviso na UI baseado no `esp` medido, não no
   formato do arquivo.

### 5.2 O falso positivo não é cosmético — ele quebra a armadura

Correlação observada: quando o FP sobe, `nome` cai, com `grau` intacto em 100%.

Mecanismo: `armadura()` decide o que é armadura por `colada()` — distância do acidente até
a **primeira nota** do sistema (< 0,25 span = acidente da nota; ≥ 0,49 span = armadura).
Uma cabeça falsa à esquerda do sistema muda quem é "a primeira nota", o acidente de
armadura passa a parecer colado numa nota, e a armadura inteira é descartada. Todos os
nomes daquele sistema saem sem alteração.

**Consequência de projeto:** num modo bitmap, precisão de cabeça é mais crítica que
recall. Perder uma cabeça custa uma nota; inventar uma cabeça no lugar errado custa um
sistema inteiro.

### 5.3 Por que o FP é irredutível com visão clássica

As três fontes de FP são **ambíguas por construção** num bitmap:

| fonte | por que não dá para separar por geometria |
|---|---|
| nome de nota impresso | a letra "o" de "Do" **é** uma elipse cheia do tamanho certo, na altura certa |
| pausa de semínima/colcheia | tem bojo preenchido de tamanho comparável |
| clave | contém dois bojos elípticos preenchidos |

No modo vetor nenhuma delas é problema: texto tem fonte, pausa e clave têm codepoint. A
informação que resolve não é geométrica — ela foi **destruída pela rasterização**. Nenhum
ajuste de limiar recupera o que não está mais na imagem; o que resolve é um classificador
que aprendeu a aparência das três classes.

### 5.4 A armadilha de escala, confirmada

`pautas()` usa `k = altura_pagina / 842` para o passo plausível entre linhas
(`2,0·k ≤ gap ≤ 14,0·k`) e para `junta_max`. Num screenshot o `k` não tem significado.

| cadernin | níveis de linha achados | pautas |
|---|---|---|
| p0 | 5 | 0 |
| p3 | 0 | 0 |
| p10 | **31** | **0** |
| p40 | — | 4 → cabeças 98,0%, grau 100%, FP 23 |

A p10 é a prova: havia 31 níveis de linha detectados e nenhuma pauta se formou. **Primeiro
conserto obrigatório de um modo bitmap real:** derivar o `k` do passo medido entre linhas
(que sai da própria projeção horizontal), não da altura da página.

---

## 5.5 Segunda rodada: resolver o FP SEM CNN

A §5.3 concluiu que o FP era irredutível por geometria. **Estava errada** — porque olhava
só para a *aparência* da mancha. Trocando a pergunta de "isso **parece** uma nota?" para
"isso **se comporta** como nota?", o FP cai de ~9% para 3,7% no total.

### Ponto de operação consolidado (defaults do módulo)

| PDF | cabeças | grau | nome | FP |
|---|---|---|---|---|
| Marlon Blanco | 98,1% | 100% | 94,8% | 3 (1,9%) |
| Song_of_somg | 75,9% | 100% | **100%** | **0** |
| Paso Corto | 97,3% | 100% | **100%** | 19 (7,3%) |
| cadernin p40 (contorno) | 98,0% | 100% | 96,9% | **0** |
| **total (601 notas)** | **94,5%** | **100%** | — | **22 (3,7%)** |

### As regras testadas, uma por uma

| regra | ideia | efeito medido |
|---|---|---|
| **cabeça só do detector** | blob bruto do contorno **não** pode virar cabeça; só o detector dedicado produz cabeça | **a que mais valeu**: Song 12 FP → **0**, cadernin 14 → **0**, Marlon 4 → 3 |
| **haste obrigatória** (≥ 2,2 esp) | nota de figura ≤ mínima tem haste encostando (armadilha nº 11) | Marlon 14 FP → 4. Só funciona com `vert` restrito: com `h ≥ 1,2 esp` havia 507 verticais numa página de 156 notas e a regra não filtrava nada |
| **preenchimento da elipse** ≥ 0,80 | cabeça é bloco cheio; letra "o" e pausa são anel/zigzag | FP a ~1/2, custa ~7 pontos de recall |
| **alinhamento a meio-espaço** ≤ 0,18 | cabeça mora em linha ou espaço | FP a ~3/4, custo de recall quase nulo |
| **banda de texto por baseline** | nota sobe e desce; letra senta numa baseline comum | Marlon 14 → 9 FP, mas −2,6 de recall. Não pega cifra isolada |
| **isolamento (coroa em volta)** | beam espesso preenche a coroa, cabeça não | **nenhum efeito** |
| **linha suplementar obrigatória** | nota longe da pauta exige ledger; cifra não tem | **nenhum efeito**, e −4 de recall |

### Por que "cabeça só do detector" foi decisiva

Estava havendo **duas portas de entrada** para cabeça: o detector (com todos os filtros) e
o `glifos_de_contorno` lendo os blobs brutos por `CABECA_W`/`CABECA_H`. A segunda porta não
passava por filtro nenhum — por isso as regras novas não surtiam efeito. Foi o que explicou
os "19 FP que não reagiam a nada". Correção: `sem_cabeca()` remove dos blobs tudo com
tamanho de cabeça, e eles seguem servindo só para clave, acidente e ponto.

### O gargalo agora é a SEMIBREVE

O recall de 75,9% do Song_of_somg tem causa única e identificada: as 21 perdas são **todas
notas vazadas** — 14 semibreves/longas e 7 mínimas. **Semibreve não tem haste**, então a
regra da haste as executa junto.

Tentativa: liberar cabeça vazada da exigência de haste. Recall 75,9% → 83,9%, mas o FP
volta (Marlon 3 → 13, cadernin 0 → 19), porque "vazado sem haste" é exatamente a assinatura
da letra "o" de um nome impresso. Aumentar a área de miolo tapado (0,85 → 1,6 → 2,5 esp²)
só piorou o recall. **Trade-off direto, não resolvido nesta rodada.**

Saída natural (não testada): a semibreve tem assinatura própria — vazada **e** ~1,75 esp de
largura contra 1,30 da cabeça normal. Um **segundo template**, com sua própria regra (não
exige haste), separaria semibreve de letra "o" por largura. Isso é o começo de um
**banco de templates multi-classe**: um template por figura (preta, mínima, semibreve) e um
por glifo concorrente (pausa, clave), decidindo por `argmax` de correlação em vez de por
limiar. Os templates saem recortados dos PDFs vetoriais do acervo, onde a posição de cada
glifo é conhecida — mesma fonte de dados que treinaria uma CNN, mas consumida como
vizinho-mais-próximo: determinístico, em numpy puro, sem ONNX, e cabe no Pyodide.

### Correção do veredito da §5.3

O que a §5.3 dizia — "a informação que resolve não é geométrica, foi destruída pela
rasterização" — vale para **aparência isolada**. Não vale para **contexto de notação**: a
haste, a grade de meio-espaço e a exclusividade do detector recuperam a maior parte do que
parecia perdido, e são regras de música, não de imagem.

## 5.6 Terceira rodada: banco de templates multi-classe — fecha sem CNN

Implementado em `~/notes-pdf/_exploracao/banco_templates.py`.

**Ideia:** em vez de UM template de elipse com limiar, **um template por classe de glifo**,
e a decisão sai do `argmax` de correlação. Pausa, clave e texto passam a ser rejeitados
**positivamente** ("isso é uma pausa"), não por não passar num corte.

Os templates saem de graça dos PDFs vetoriais: o vetor diz **onde** está cada glifo e
**qual** glifo é. Mesma fonte de dados que treinaria uma CNN, consumida como
vizinho-mais-próximo — determinístico, numpy puro, sem ONNX, cabe no Pyodide.

### Protocolo

- **Treino:** Strasbourg_St_Denis p0 + The-chicken p0/p1. O The-chicken é **Sibelius
  (fonte Sonata)**, então o banco vê duas famílias de fonte.
- **Teste:** os 4 de sempre. **Obras diferentes das de treino** — montar o banco com o
  arquivo que se avalia mediria a memória do banco, não a generalização.
- Patch: janela de 2,4 espaços centrada no glifo, reamostrada a 24×24, média zero e norma
  1. Normalizar pelo espaço de pauta é o que faz o template servir em qualquer zoom.
- Classes reduzidas por k-médias: 6 representantes cada, 18 para `outro` e `texto`.

| classe | amostras → templates |
|---|---|
| preta | 215 → 6 |
| pausa | 67 → 6 |
| minima | 21 → 6 |
| acc / bandeira / clave / ponto | 30 / 21 / 14 / 8 → 6 cada |
| texto | 156 → 18 |
| outro (beam, arco, barra, hairpin) | 1191 → 18 |
| **semibreve** | **1 → 1** |

`outro` é amostrado numa grade determinística sobre a região das pautas, em pixels de tinta
longe de qualquer glifo ou texto conhecido.

### Resultado — melhora as DUAS métricas ao mesmo tempo

| PDF | cabeças | grau | nome | FP |
|---|---|---|---|---|
| Marlon Blanco | **100%** | 100% | 94,2% | 5 (3,2%) |
| Song_of_somg | 82,8% | 100% | **100%** | **0** |
| Paso Corto | 99,6% | 100% | **100%** | 3 (1,2%) |
| cadernin p40 (contorno) | 96,0% | 100% | 96,8% | 2 (2,0%) |
| **total (601 notas)** | **96,7%** | **100%** | — | **10 (1,7%)** |

Comparação das três rodadas:

| rodada | cabeças | grau | FP |
|---|---|---|---|
| §5.3 template único + limiar | 84–98% | 100% | ~9% |
| §5.5 + regras de notação | 94,5% | 100% | 3,7% |
| **§5.6 + banco multi-classe** | **96,7%** | **100%** | **1,7%** |

### O banco não substitui o contexto — precisa dos dois

| config | cabeças | FP |
|---|---|---|
| banco sozinho (margem 0) | 97,2% | **61,1%** |
| banco sozinho (margem 0,12) | 96,8% | 10,8% |
| banco + contexto (margem 0) | 97,0% | 6,2% |
| **banco + contexto (margem 0,12)** | **96,7%** | **1,7%** |

`margem` = folga exigida do melhor template de cabeça sobre o melhor template
não-cabeça. Entre 0,10 e 0,12 o resultado é idêntico; a 0,16 o FP cai para 1,3% mas o
recall despenca para 94,3%.

**Por que os dois:** o classificador diz *o que* a mancha é; o contexto diz se ela *pode
estar ali*. O banco sozinho aceita qualquer coisa parecida com cabeça em qualquer posição.
E o banco é o que **liberta a semibreve** da regra da haste: como a classe é conhecida,
a exigência de haste se aplica a `preta`/`minima` e não a `semibreve`.

### Vias fechadas (medidas, não supostas)

- **Semibreve sintética.** Com só 1 amostra de treino, desenhei 3 elipses vazadas largas e
  pus no banco. **Piorou**: Song 82,8% → 80,5%. A elipse desenhada não tem a aparência da
  rasterizada (antialias, peso do traço) e ainda rouba candidatos do template real.
- **Isolamento por coroa** e **linha suplementar obrigatória** (§5.5): zero efeito.

### O que ainda limita

O recall de 82,8% do Song_of_somg continua sendo **cabeça vazada**, e a causa agora é
óbvia: **1 amostra de semibreve no treino**. Não é limitação do método, é falta de dado —
e o acervo tem 1145 PDFs para resolver isso. É o primeiro experimento a rodar se isso
for adiante.

### Veredito

**Dá para fechar sem CNN.** Com banco multi-classe + regras de notação: **96,7% de cabeça,
100% de grau, 1,7% de FP**, treinado em 2 obras e testado em 4 outras, incluindo um PDF em
modo contorno e uma fonte diferente (Sonata) das do treino. Uma CNN provavelmente
melhoraria o recall, mas custaria o `onnxruntime` — que não existe no Pyodide — e portanto
o "um `.py` só para CLI e web".

## 6. O que NÃO foi testado

Lacunas honestas, em ordem de risco:

1. **Screenshot de verdade.** O mock renderiza com PyMuPDF. Um screenshot real tem
   subpixel rendering do compositor da tela, escala fracionária, barra de status, recorte,
   e possivelmente tema escuro. Nada disso está coberto.
2. **Ritmo.** `beams=[]` no mock. A duração sai errada; o `_` de nota segurada e a
   ligadura não foram avaliados.
3. **Pausa.** Não produzo pausa, então o compasso não fecha e o player de piano não teria
   o relógio certo.
4. **Fonte Sonata (Sibelius/Finale).** Só MuseScore e um PDF em modo contorno foram
   testados. `The-chicken.pdf` não entrou.
5. **Acorde, apojatura, clave de fá.** Não avaliados.
6. **Mais de uma página por arquivo**, e o acervo inteiro. As medições são de 1 página de
   4 arquivos.
7. **Custo em Pyodide.** Tempo e memória do opencv no navegador não foram medidos — só
   confirmei que o wheel existe (11 MB).

---

## 7. Rotas a partir daqui

| rota | escopo | ganho esperado | risco |
|---|---|---|---|
| **A. Consertar a escala** | derivar `k` do passo entre linhas em vez da altura da página | destrava as páginas do cadernin; pré-requisito de tudo | baixo — mas mexe em `pautas()`, que serve o modo vetor também |
| **B. CNN pequena para cabeça** | trocar só `cabecas_por_template`; dataset gerado do acervo (render + posição do vetor) | é a rota que ataca o FP na raiz (§5.3) | precisa treinar e exportar ONNX; `onnxruntime` **não existe no Pyodide** → rodaria em `onnxruntime-web` (JS), quebrando o "um `.py` só" |
| **C. Filtro de FP por contexto musical** | descartar cabeça sem haste/beam plausível, ou fora da grade de x das outras notas | barato, ataca pausa e clave | não resolve o nome impresso |
| **D. Modo bitmap oficial** | `coletar()` aceita imagem; saída = imagem virada PDF + camada de texto | fecha o produto | só vale depois de A + (B ou C) |

**Ordem que eu seguiria: A → C → medir → decidir se B é necessário.** A rota B tem um
custo arquitetural alto (mata o "mesmo `.py` na CLI e na web") e talvez o C já leve o FP a
um nível onde o corretor de régua ([[PESQUISA-EDITOR.md]]) resolve o resto.

---

## 8. Como reproduzir

```bash
cd ~/notes-pdf
# um arquivo, com imagem de debug (círculo verde em cada cabeça lida)
uv run --with opencv-python-headless --with numpy --with pymupdf \
  python _exploracao/mock_bitmap.py "<pdf>" 0 1.97 --debug

# artefato de JPEG
... python _exploracao/mock_bitmap.py "<pdf>" 0 1.97 --jpeg=60
```

Knobs no topo do módulo: `FILL_MIN` (preenchimento mínimo), `ALINHA_MAX` (desvio máximo do
meio-espaço), `TIRAR_HASTE` (deixar `False` — ver §4 iteração 4). O limiar de correlação é
o 6º argumento de `comparar()`.

Saída do `--debug`: `debug_bitmap.png` (overlay) e `debug_bitmap_limpo.png` (imagem após
remoção da pauta) — o segundo é o que mostra se a limpeza comeu glifo.
