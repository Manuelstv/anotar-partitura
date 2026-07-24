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
| `~/notes-pdf/` | este repo (dev). `anotar_partitura.py` é o arquivo que importa |
| `~/anotar-partitura-web/` | cópia publicada: `index.html` + o mesmo `.py` |
| `github.com/Manuelstv/anotar-partitura` | repo público, Pages no branch `master` |
| `https://manuelstv.github.io/anotar-partitura/` | site — arrasta PDF, baixa anotado |
| `C:\Users\ManuelSperanzaTorres\Anotar partitura.bat` | atalho Windows de arrastar-soltar (+ variante `(Do-Re-Mi).bat`) |

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
6. Ao mudar a assinatura de `coletar()`, atualizar `validar2.py` e `_exploracao/*.py`.

## Como medir (fazer isso a cada mudança no núcleo)

Há **duas** métricas, e as duas importam:

- **Acurácia** — contra partituras que já traziam os nomes impressos, casando nota↔nome
  por coluna x. `validar2.py <pdf> [letras|dore] [tol_x] [acima|abaixo]` para um arquivo;
  `_exploracao/validar_lote.py <raiz> "with note names" abaixo` para o acervo.
- **Cobertura** — quantas das cabeças presentes no PDF receberam rótulo.
  `_exploracao/levantar.py <raiz> saida.csv` + `_exploracao/analisar.py saida.csv`.
  Cobertura baixa = pauta não detectada.

Casos de regressão obrigatórios (em `~/Downloads`): `Marlon Blanco - Negra ron y
velas-Saxofone_Alto.pdf` (MuseScore, 100%), `The-chicken.pdf` (Sibelius, 98% — as 2
divergências são erro do próprio PDF, confirmado pela transposição alto→tenor),
`Strasbourg_St_Denis_*.pdf` (página 5×, 121/121), `Song_of_somg.pdf` (1ª nota deve dar
`E#`), `cadernin_2026_sax alto (2).pdf` (modo contorno, 253 páginas).

O acervo de validação é o zip `sax-*.zip` do Manuel (Online Sax Academy): 1145 PDFs, dos
quais **182 vêm em versão "With Note Names"** — é o gabarito em escala. Ele é extraído em
diretório temporário, não versionado.

## Limites conhecidos (não são bugs)

- **PDF escaneado (imagem) não funciona.** Sem vetor não há coordenada.
- **Pauta de ritmo (1 linha) não recebe nome** — não existe altura para nomear. É a maior
  parte da cobertura que falta.
- Clave de fá e de dó estão implementadas mas **não testadas** (o caso do Manuel é sax,
  sempre clave de sol).
- Nota ligada recebe o nome repetido.
- Acorde (várias notas no mesmo x) empilha os nomes; pouco testado.
