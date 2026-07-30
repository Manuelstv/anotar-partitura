# Anotar partitura a partir de SCREENSHOT (PNG/JPG)

Pesquisa de viabilidade — 2026-07-29. **Decisão do Manuel: o caso de uso é
*screenshot* (print da tela do celular), não foto de papel.** Isso muda o veredito de
"outro projeto" para "um módulo novo".

## Veredito

**Viável**, e sem tocar no núcleo. O programa não precisa *entender* a partitura: precisa
só de duas coisas que hoje o PDF entrega de graça — **onde estão as 5 linhas da pauta** e
**onde estão as cabeças**. Toda a aritmética de altura, a armadura, e o `escrever()`
continuam valendo sem uma linha de mudança.

Screenshot é o caso fácil porque é *o mesmo pixel que o renderizador desenhou*: sem
perspectiva, sem sombra, sem glare, pauta perfeitamente horizontal, contraste alto.
É praticamente o PDF, só sem as coordenadas escritas.

## Ponto de encaixe: um quarto modo, `bitmap`

O modo **contorno** (`glifos_de_contorno`) já lê partitura sem fonte musical, por
geometria pura medida **em espaços de pauta**. É exatamente a interface que o bitmap
precisa preencher. `coletar()` devolve
`(glifos, textos, horiz, vert, formas, caminhos[, beams])` — o modo bitmap tem de produzir
**`horiz`** e **`caminhos`** a partir de pixels, e o resto do pipeline segue igual.

| Etapa | Hoje (PDF vetor) | No screenshot |
|---|---|---|
| linhas da pauta (`horiz`) | vetor dado | projeção horizontal de pixels escuros → picos periódicos (o `pautas()` por periodicidade já cuida do resto) |
| cabeças (`caminhos`) | curvas dadas | morfologia: erosão/abertura com kernel elíptico, ou template matching por componente conexo |
| vazada vs. preta | `c["curvas"] >= 2` | fração de pixels escuros dentro da elipse |
| hastes/beams (`vert`) | vetor | linhas verticais por projeção; beam = blob espesso e inclinado |
| altura, armadura, nome | inalterado | inalterado |
| saída | PDF + camada de texto | imagem vira PDF de 1 página (`fitz`), depois `escrever()` igual |

O requisito central se mantém: **nada é re-desenhado**. A imagem original é o fundo, o
nome das notas é uma camada de texto por cima.

## Roda no site (confirmado no lock do Pyodide 0.28.3, a versão que o `index.html` usa)

| Pacote | Versão | Wheel |
|---|---|---|
| `opencv-python` | 4.11.0.86 | 11 MB |
| `scikit-image` | 0.25.2 | 9 MB |
| `scipy` | 1.14.1 | 12 MB |
| `numpy` | 2.2.5 | — |
| `Pillow` / `pillow-heif` | 11.3.0 / 1.0.0 | — (o `heif` importa porque iPhone salva HEIC) |
| `PyMuPDF` | 1.26.3 | já em uso |

Ou seja: dá para fazer com **o mesmo `.py` rodando na CLI e no navegador**, sem porte, sem
wheel hospedado, sem backend. Só `numpy` + `opencv` bastam para o pipeline acima —
`scikit-image`/`scipy` são opcionais (evitar, para não somar 21 MB de download).

## MOCK RODADO — 2026-07-29

> Análise completa (metodologia, log de iterações, diagnósticos, rotas) em
> [[MOCK-SCREENSHOT-ANALISE.md]]. O que segue é o resumo.

Protótipo em `~/notes-pdf/_exploracao/mock_bitmap.py`. Renderiza o PDF como se fosse
screenshot (`get_pixmap` no zoom da tela, opcionalmente com artefato de JPEG), produz
`horiz` + `caminhos` por pixels, faz **monkeypatch de `coletar()`** e roda `ler_notas()`
sem tocar no núcleo. O **PDF vetorial é o gabarito** — divergência = erro do bitmap.

O encaixe previsto funcionou: `pautas()` e `glifos_de_contorno()` aceitaram os dados de
pixel sem alteração nenhuma.

### O que ficou de pé

**Altura: 100% de grau diatônico correto em todas as condições testadas** — 4 PDFs, zoom
1,2 / 1,97 / 3,0, com e sem JPEG q60, MuseScore e modo contorno. Zero exceção. A
aritmética de altura é reusável tal como está.

| PDF | pautas | cabeças achadas | grau | nome completo | FP |
|---|---|---|---|---|---|
| Marlon Blanco (MuseScore) | 7 | 100% (156/156) | **100%** | 100% | 14–150¹ |
| Song_of_somg | 9 | 84% | **100%** | 98,6%² | 25 |
| Paso Corto | 10 | 97–100% | **100%** | 100%² | 30 |
| cadernin p40 (contorno) | 4 | 98% | **100%** | — | 23 |

¹ o FP varia com o limiar de correlação — ver abaixo. ² só com a haste preservada.

### Piso de resolução: ~8 px por espaço de pauta

O recall de cabeça é governado pelo espaço de pauta em **pixels**, não pelo tamanho do
arquivo:

| zoom | espaço | cabeças achadas | grau |
|---|---|---|---|
| 1,2 | 6,0 px | **44%** | 100% |
| 1,97 | 9,8 px | 98% | 100% |
| 3,0 | 14,8 px | 97% | 100% |

JPEG q60 quase não atrapalha com resolução boa (98% em 14,8 px), mas derruba para 80%
quando a resolução já está no limite (9,8 px). **Regra prática: exigir ~10 px por espaço
de pauta**, o que num A4 inteiro dá largura ≥ ~1100 px — qualquer celular moderno entrega
isso num screenshot de tela cheia.

### O gargalo é o detector de cabeça, e ele contamina a armadura

Detecção por correlação com template de elipse (o método clássico) dá recall alto mas
**20–30% de falso positivo**, e não há limiar que resolva os dois:

| limiar | cabeças | FP |
|---|---|---|
| 0,55 | 100% | 150 |
| 0,65 | 98% | 35 |
| 0,75 | 81% | 1 |

Dois discriminantes extras (preenchimento da elipse ≥ 0,80; centro alinhado a meio-espaço
da pauta) cortam o FP para ~1/3, e não mais que isso.

De onde vem o FP, medido contra o vetor: **nome de nota já impresso na partitura** (a
letra "o" de "Do" é uma elipse cheia), **pausa**, e **clave**. No modo vetor isso nunca
foi problema porque texto é texto e pausa tem codepoint; no bitmap tudo é mancha.

E o FP não é cosmético: cabeça falsa perto do início do sistema **quebra a detecção de
armadura** (`colada()` compara com a primeira nota), e aí todo nome sai sem alteração.
Foi o que derrubou o "nome completo" para 58% em duas medições.

### Duas armadilhas que o mock cobrou na hora

1. **Apagar haste apaga o sustenido.** O sustenido também é dois traços verticais
   compridos e estreitos. Remover haste por geometria levou o nome completo de 98,6% para
   22,8%. Com a cabeça vinda de correlação (e não de componente conexo), não há motivo
   para remover haste — a correção é não remover.
2. **Tapar todo buraco fechado inunda a partitura.** Preencher o miolo da mínima é
   necessário para ela sobreviver ao detector; mas o flood fill também preenche a área
   cercada por haste + beam + cabeça vizinha, que é enorme, e a correlação desaba. Tapar
   só buraco com área ≤ ~0,85 espaço².

### Veredito do mock — fecha SEM CNN

A espinha dorsal (pauta → aritmética → nome) funciona e é reusável como está. O detector de
cabeça, que era o gargalo, foi resolvido em duas rodadas **sem rede neural**:

| rodada | cabeças | grau | FP |
|---|---|---|---|
| template único + limiar | 84–98% | 100% | ~9% |
| + regras de notação (haste, meio-espaço, porta única) | 94,5% | 100% | 3,7% |
| **+ banco de templates multi-classe** | **96,7%** | **100%** | **1,7%** |

O banco (`_exploracao/banco_templates.py`) tem um template por classe de glifo — preta,
mínima, semibreve, pausa, clave, acidente, texto, outro — e decide por `argmax` de
correlação, recortando os exemplares dos PDFs vetoriais do acervo, onde o vetor diz onde
cada glifo está e qual é. Determinístico, numpy puro, sem ONNX, cabe no Pyodide.
Treinado em 2 obras, testado em 4 outras (incluindo modo contorno e a fonte Sonata, ausente
do treino).

Uma CNN provavelmente subiria o recall, mas custaria o `onnxruntime` — que não existe no
Pyodide — e com ele o "um `.py` só para CLI e web". **Não vale, pelo menos não agora.**

## Armadilha nova: a referência de escala muda

Hoje tudo escala por `escala(pg) = altura/842`, porque o PDF tem tamanho de página
conhecido. **Screenshot não tem** — o DPI é arbitrário e depende do celular e do zoom. A
referência tem de ser o **espaço de pauta medido em pixels** (distância entre duas linhas
consecutivas), que sai da própria detecção. Isso é coerente com a armadilha nº 1 do
`CLAUDE.md`: nunca limiar em unidade absoluta.

**Confirmado no mock:** o `pautas()` usa `k = altura_pagina/842` para os limiares de passo
entre linhas. Em três páginas do cadernin (p0, p3, p10) ele devolveu **nenhuma pauta**
mesmo com 31 níveis de linha detectados, porque a página não é A4 e o `k` derrapou. A p40
do mesmo arquivo, que cai numa proporção compatível, deu 98% de cabeça e 100% de grau. É
o primeiro conserto obrigatório de um modo bitmap de verdade.

## O que se perde (e é preciso decidir antes)

1. **Ritmo.** Sem codepoint, a figura sai de preenchimento + haste + beam. É o mesmo
   buraco que o modo contorno já tem (ritmo em ~34%). O nome da nota, que é o objetivo,
   não depende disso.
2. **Toda a `analise.py`.** Cifras, tom, escalas sugeridas e o `--limpar` dependem de
   **spans de texto** do PDF. Numa imagem não existe span — precisaria OCR, que é um
   projeto à parte. Na prática: modo screenshot entrega nome de nota, **não** entrega
   análise musical.
3. **Acurácia.** Espera-se alta (mesma ordem do modo contorno), mas **não** os 99,51% do
   modo vetor. Precisa de gabarito próprio: screenshots das partituras "With Note Names"
   do acervo, comparadas com a leitura do PDF original — o PDF vira o gabarito perfeito da
   imagem.

## Caminhos descartados

**oemer**, **homr**, **Audiveris** — as melhores OMR de foto de celular disponíveis:

- Devolvem **MusicXML**, isto é, **re-engravam a partitura**. É exatamente a classe de
  solução que este projeto já rejeitou.
- Não há `onnxruntime` no Pyodide → quebraria o "um `.py` só para CLI e web"; viraria JS
  separado com `onnxruntime-web`.
- `oemer`: 3–5 min por imagem **com GPU**; checkpoints levam até 10 min para baixar.
  Expõe bbox de cabeça em `xyxy`, então poderia servir como *detector* — mas é ordens de
  magnitude mais complexo do que achar bolinha em screenshot limpo.
- `homr` (vision transformer, o melhor dos três em robustez): **não dá coordenada de
  pixel**, só o "centro de atenção" da attention. Inútil para estampar em cima.
- `Audiveris`: 80–90% em impresso limpo, 60–75% em partitura complexa. É Java.

## Referências

- oemer — https://github.com/BreezeWhite/oemer
- homr — https://github.com/liebharc/homr
- Audiveris, acurácia — https://audiveris.com/how-accurate-is-audiveris-music-recognition/
- Sheet Music Transformer — https://arxiv.org/pdf/2402.07596
- pacotes do Pyodide — https://pyodide.org/en/stable/usage/packages-in-pyodide.html
