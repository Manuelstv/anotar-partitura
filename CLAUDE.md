# anotar_partitura — contexto para agentes

Ferramenta pessoal do **Manuel Speranza Torres** (sax alto). Escreve o **nome de cada
nota embaixo da pauta**, direto no PDF da partitura. Saída = PDF original + uma camada
de texto. **Nada é re-desenhado** — o layout do arranjador fica intacto. Isso não é
detalhe de implementação, é o requisito central: soluções que re-engravam a partitura
foram rejeitadas.

Responder em **PT-BR**. Código, comentários e mensagens de commit em PT-BR (sem acento
no código, para evitar problemas de encoding).

## Onde as coisas estão

| Caminho | O que é |
|---|---|
| `~/notes-pdf/` | este repo (dev). `anotar_partitura.py` é o núcleo |
| `analise.py` | análise musical determinística (tom, cifras, soletração, escalas, pontos difíceis) |
| `dificuldade.py` + `pesos_dificuldade.json` | nota 0–10 de dificuldade no sax alto; `calibrar` reajusta os pesos |
| `~/anotar-partitura-web/` | cópia publicada: `index.html` + o mesmo `.py` |
| `github.com/Manuelstv/anotar-partitura` | repo público, Pages no branch `master` |
| `https://manuelstv.github.io/anotar-partitura/` | site — arrasta PDF, baixa anotado |
| `C:\Users\ManuelSperanzaTorres\Anotar partitura.bat` | atalho Windows de arrastar-soltar (+ variante `(Do-Re-Mi).bat`) |

O site carrega `anotar_partitura.py`, `analise.py`, `dificuldade.py` e
`pesos_dificuldade.json` no Pyodide — os **mesmos** arquivos da CLI.

**O `.py` é um só para CLI e web.** Ao alterá-lo, copiar para `~/anotar-partitura-web/` e
subir. `git push` está bloqueado por permissão neste ambiente: usar
`gh api -X PUT repos/Manuelstv/anotar-partitura/contents/<arquivo>` com o `sha` atual. Ao
mexer no `.py`, incrementar `?v=N` no `fetch` dentro do `index.html`, senão o navegador
serve a versão em cache.

O site roda **Pyodide 0.28.3 + PyMuPDF**, que já vem embutido no Pyodide
(`loadPackage("pymupdf")`) — sem wheel para hospedar, sem CORS. Por isso o mesmo `.py`
roda no navegador sem porte nenhum, e a precisão é idêntica à do CLI.

## Como funciona (a ideia central)

**Não é OCR nem rede neural.** Partitura gerada por computador guarda cada cabeça de nota
como *caractere de uma fonte musical* (ou como *curva*), e as linhas da pauta como vetor.
A altura sai por **aritmética sobre coordenadas** — nos testes, a menos de **0,05
meio-espaço** do valor exato. Pipeline:

1. `pautas()` — linhas horizontais → pautas, por **periodicidade** (5 linhas de passo
   igual), não por adjacência;
2. glifos → clave, armadura, acidentes, cabeças (3 modos, abaixo);
3. altura = meio-espaços acima da linha de topo + `topo_ref` da clave;
4. armadura + acidente explícito + acidente vale até a barra de compasso;
5. `escrever()` estampa embaixo da pauta, abaixo de hastes/ligaduras, 2ª fileira quando
   colide.

### Três modos de leitura de glifo

| Modo | Quando | Como |
|---|---|---|
| `smufl` | MuseScore, Dorico (Leland, Bravura, Petaluma) | codepoints SMuFL |
| `sonata` | Sibelius (Opus), Finale (Maestro) | layout legado Adobe Sonata |
| contorno | PDF com os glifos **convertidos em curvas** (sem fonte) | geometria, em espaços de pauta |

O modo contorno (`glifos_de_contorno`) ativa **sozinho** quando a página não tem fonte
musical. Assinaturas medidas no acervo do Manuel: cabeça `1,30 × 1,06` preenchida com
curva; sustenido `0,98 × 2,67`; bequadro `0,68 × 2,59`; bemol `0,81 × 2,52` com a nota
meio espaço abaixo do centro da caixa; clave altura > 5,5.

## Armadilhas que já custaram caro — não reintroduzir

1. **Nunca usar limiar de geometria em pontos absolutos.** O mesmo A4 aparece gravado em
   escalas diferentes (visto 595×842 e 2976×4209 na mesma pasta). Tudo escala por
   `escala(pg)` = altura/842, e os valores são os já validados em A4.
2. **O bbox de caractere do PyMuPDF tem a altura da LINHA de texto, não da tinta.** A
   posição real da cabeça é `centro_do_bbox + 0.5*size*(ascender+descender)`. Isso
   substituiu um deslocamento constante por família de fonte, que estava errado — as
   métricas variam de arquivo para arquivo.
3. **Ao juntar níveis de linha quase coincidentes, medir a UNIÃO dos segmentos, nunca a
   soma.** Somando, traços curtos empilhados viram "linha longa" fantasma e a pauta sai
   deslocada uma linha inteira (leitura 2 graus errada).
4. **Armadura ≠ "acidente antes da primeira nota".** O acidente da 1ª nota fica a
   ~0,09 span dela; o de armadura, a ≥0,49 span. Limiar em `0,25 span` (`colada()`).
   **Não** checar as letras canônicas (F C G D…) para validar armadura: a posição
   vertical do glifo de bemol não é a da nota e isso rejeita armadura de bemol.
5. **`--limpar` é heurístico e tem duas travas** (≥50% das notas com nome, e só a família
   dominante). O acervo tem letras de música em PT-BR onde "A" e "E" são palavras — sem
   as travas, viraria tarja branca em cima da letra.
6. Ao mudar a assinatura de `coletar()`, atualizar `validar2.py`, `analise.py` e
   `_exploracao/*.py`.
7. **Cifra vs. nome de nota vs. marca de ensaio** (`analise.ler_cifras`): o nome de nota
   escrito embaixo de um sistema cai na faixa "acima" do sistema seguinte — o teto tem de
   ser o MEIO do vão. Marca de ensaio ("A", "B") casa com a regex de cifra e é separada
   por estar dentro de uma caixa desenhada. E o `7` da cifra é sobrescrito, span à parte:
   sem juntar, "G7" vira "G" e a escala sugerida sai errada.
8. **Cifra vem partida em vários spans.** `Amaj7` = `A` + `maj7`; `Gadd9/C` = `G` +
   `add9` + `/C`. A junção tem de aceitar sufixo com LETRAS e baixo de barra, e continuar
   juntando sobre um acumulado que já tem sufixo. Calibrar só no The-chicken engana: lá
   todas as cifras são numéricas (`G7`, `C7`).
9. **Soletrar acorde pelo GRAU diatônico**, nunca por tabela fixa de sustenidos/bemóis:
   senão C7 sai "A#" em vez de "Bb". E `add9`/`6/9` não levam sétima.
10. Na nota de dificuldade, os pesos são **não-negativos** de propósito: sem essa
   restrição a colinearidade dava peso negativo para salto, ou seja, "salto grande
   facilita". Validar sempre fora da amostra (5 folds) e pela ordenação da mesma música
   em níveis diferentes — é a métrica que importa.

**Padrão que já se repetiu duas vezes:** calibrar num único arquivo e generalizar cedo
(o deslocamento fixo das fontes Sonata; a junção de cifra só numérica). Ao criar qualquer
regra a partir de um exemplo, rodar em pelo menos mais dois arquivos de origem diferente
antes de considerar pronto. E depois de refatorar `analise.py`, rodar a análise num PDF
de verdade — teste de função isolada não pega `NameError` no caminho completo.

## Como medir (fazer isso a cada mudança no núcleo)

Há **duas** métricas, e as duas importam:

- **Acurácia** — contra partituras que já traziam os nomes impressos, casando nota↔nome
  por coluna x. `validar2.py <pdf> [letras|dore] [tol_x] [acima|abaixo]` para um arquivo;
  `_exploracao/validar_lote.py <raiz> "with note names" abaixo` para o acervo.
- **Cobertura** — quantas das cabeças presentes no PDF receberam rótulo.
  `_exploracao/levantar.py <raiz> saida.csv` + `_exploracao/analisar.py saida.csv`.
  Cobertura baixa = pauta não detectada.

Para a dificuldade: `uv run dificuldade.py calibrar <raiz>` reporta R² dentro e fora da
amostra e a taxa de ordenação. Hoje: R²cv 0,445 e **91,7%** de ordenação correta. O que
falta é o RITMO — não leio duração, e é o fator que mais separaria os níveis.

Casos de regressão obrigatórios (em `~/Downloads`): `Marlon Blanco - Negra ron y
velas-Saxofone_Alto.pdf` (MuseScore, 100%), `The-chicken.pdf` (Sibelius, 98% — as 2
divergências são erro do próprio PDF, confirmado pela transposição alto→tenor),
`Strasbourg_St_Denis_*.pdf` (página 5×, 121/121), `Song_of_somg.pdf` (1ª nota deve dar
`E#`), `cadernin_2026_sax alto (2).pdf` (modo contorno, 253 páginas).

O acervo de validação é o zip `sax-*.zip` do Manuel (Online Sax Academy): 1145 PDFs, dos
quais **182 vêm em versão "With Note Names"** — é o gabarito em escala. Ele é extraído em
diretório temporário, não versionado.

## Pendências

`PENDENCIAS.md` tem a lista viva, em ordem de prioridade. A primeira é: **nota ligada
deve receber um nome só, com `_`** (hoje sai `G G G` onde deveria sair `G_`).

## Limites conhecidos (não são bugs)

- **PDF escaneado (imagem) não funciona.** Sem vetor não há coordenada.
- **Pauta de ritmo (1 linha) não recebe nome** — não existe altura para nomear. É a maior
  parte da cobertura que falta.
- Clave de fá e de dó estão implementadas mas **não testadas** (o caso do Manuel é sax,
  sempre clave de sol).
- Nota ligada recebe o nome repetido.
- Acorde (várias notas no mesmo x) empilha os nomes; pouco testado.
