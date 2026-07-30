# Pendências

Lista viva do que ficou por fazer. Ordem = prioridade.

---

## 1. ~~Nota ligada / nota longa com UM nome só e `_`~~ — RESOLVIDO

`ligaduras_de()` acha o arco (path curvo preenchido, 2–4 curvas) entre duas cabeças
**vizinhas e de mesma altura**, sem pausa no meio. A segunda perde o nome, a primeira
ganha `_` e a soma das durações. Nota longa sem ligadura (`dur >= 2`) também recebe `_`.
Funciona nos três modos de leitura, inclusive contorno.

A ligadura partida no **fim do sistema** também é costurada: meio arco sai da última
cabeça de uma pauta e meio arco chega na primeira da pauta seguinte, e `ler_notas` junta
as duas pontas depois do laço. Medido em 150 arquivos do acervo: 4,8% das cabeças ficam
presas por ligadura, com máximo de 28% num arranjo de bossa (que é ligadura mesmo).

**Falta:** ligadura entre a última pauta de uma página e a primeira da página seguinte
(`ler_notas` trabalha por página).

---

## 2. ~~Ler a DURAÇÃO das figuras~~ — RESOLVIDO

Lê cabeça (semibreve/mínima/semínima pelo codepoint), níveis de beam (geometria),
bandeirola (codepoint) e ponto de aumento. Medição: **100%** dos compassos fecham com a
fórmula nos quatro arquivos de regressão; **80%** no acervo inteiro (1203 arquivos,
66 602 compassos). Ver `_exploracao/validar_ritmo.py`.

O que ainda derruba o número no acervo:

- **Modo contorno não lê pausa.** Sem codepoint, separar pausa de semínima de um bequadro
  pela caixa delimitadora é chute — as duas medem ~1,0 × 2,7 espaços. É a maior parte do
  que falta (o cadernin sozinho fica em 34%).
- **Quiáltera** (tercina) não é lida: o compasso fecha com 1/3 a mais.
- **Bandeirola de fusa na fonte Sonata** ficou de fora: só medi colcheia (`j`/`J`) e
  semicolcheia (`r`/`R`).

---

## 3. Botar o ritmo na nota de dificuldade

Agora que a duração existe, dá para entrar no modelo: densidade real de notas por tempo,
menor figura usada, fração de síncope. Hoje o R² validado é 0,445 e `dens` (notas por
compasso) ficou com peso zero por ser proxy fraco. Refazer `dificuldade.calibrar` com as
novas colunas e conferir se a taxa de ordenação passa dos 92%.

---

## 4. Modo SCREENSHOT — aceitar print de celular (PNG/JPG)

**Estado: protótipo medido, nada integrado.** O site rejeita imagem antes de tentar
(`index.html`, validação da extensão), o núcleo não tem uma linha de bitmap, e o protótipo
vive só na CLI: `_exploracao/mock_bitmap.py` + `_exploracao/banco_templates.py`.

Medido no protótipo (601 notas, 4 arquivos, treino em 2 obras diferentes):
**96,7% das cabeças, 100% de grau diatônico, 1,7% de falso positivo** — sem CNN. Análise
completa em `MOCK-SCREENSHOT-ANALISE.md`, resumo em `PESQUISA-SCREENSHOT.md`.

Falta, nesta ordem:

1. **Consertar a referência de escala em `pautas()`.** Hoje `k = altura_pagina / 842`, que
   não significa nada num screenshot. Derivar o `k` do passo medido entre as linhas, que
   sai da própria projeção horizontal. Sintoma atual: 3 páginas do cadernin devolvem
   **zero pauta** mesmo com 31 níveis de linha detectados. **Cuidado: `pautas()` serve o
   modo vetor também** — a mudança tem de passar pelos quatro casos de regressão.
2. **Portar o modo bitmap para o núcleo.** `coletar()` aceitando imagem e produzindo
   `horiz` + `caminhos` (é o contrato que o mock injeta por monkeypatch, documentado na
   §2.3 da análise), a imagem virando PDF de uma página, e o `escrever()` estampando em
   cima como sempre. O modo contorno consome isso sem mudança.
3. **Aceitar imagem no site.** `accept`, a validação de extensão, e
   `loadPackage("opencv-python")` — +11 MB no primeiro uso, então carregar só quando a
   entrada for imagem, nunca no caminho do PDF.
4. **Testar com print de celular DE VERDADE.** O protótipo nunca viu um: ele renderiza o
   PDF com PyMuPDF e trata essa imagem como screenshot. Print real tem subpixel rendering
   da tela, escala fracionária, barra de status e recorte — nada disso está coberto.

Limites já conhecidos do modo:

- **Exige ~10 px por espaço de pauta** (A4 inteiro com largura ≥ ~1100 px). Com 6 px o
  recall cai para 44%. Avisar pelo `esp` medido, não pelo formato do arquivo.
- **A `analise.py` não funciona em imagem** — cifra, tom, escala sugerida e `--limpar`
  dependem de span de texto, que não existe num bitmap. Modo screenshot entrega nome de
  nota, não entrega análise musical.
- **Ritmo não foi avaliado** (o mock não produz beam nem pausa).
- **Semibreve é o gargalo de recall** — o banco de templates tem 1 amostra dela. Resolver
  é aumentar o treino a partir do acervo, não mexer no método.
- **Foto de papel continua fora.** Perspectiva e sombra são outro problema; o que foi
  medido é screenshot, que não tem nenhum dos dois.

---

## 5. Estimar o acorde de cada compasso quando não há cifra

Hoje, sem cifra, mostro o **campo harmônico** do tom (o que cabe). O passo seguinte é
casar as notas de cada compasso contra os sete graus e sugerir qual acorde soa —
continua determinístico, mas é **palpite** e tem de ser rotulado como tal na interface,
separado do que foi lido.

---

## 6. Forma (A / B / refrão) não aparece na interface

`analise.forma()` já existe e agrupa compassos com a mesma sequência de alturas, mas o
resultado não é exibido. Falta decidir a apresentação (uma faixa tipo `AABA`?) e tratar
repetição aproximada — hoje só casa sequência idêntica.

---

## 7. Testar no iPhone de verdade

Layout conferido em 390px: sem rolagem horizontal. Falta testar no aparelho:

- **memória** — o Safari mata aba pesada; Pyodide + PyMuPDF pede centenas de MB.
  Partitura curta deve ir; o cadernin de 253 páginas provavelmente derruba.
- **download** — `download` de arquivo gerado em memória é instável no Safari; pode
  abrir o PDF em vez de salvar. Se acontecer, oferecer um botão "abrir" alternativo.
- **áudio** — o player só cria o `AudioContext` no clique, que é o que o iOS exige.
  Não testado em aparelho.

---

## 8. Casos não cobertos (conhecidos, não são bugs)

- **`--limpar` não apaga traço de extensão.** Nas partituras que já vêm com nome, o
  traço que indica nota longa é um desenho, não texto, e a tarja branca só cobre texto.
  Sobra um risquinho por cima do nome novo.
- **PDF escaneado / foto de papel** — sem vetor não há coordenada, e perspectiva e
  sombra pedem OMR de verdade (Audiveris/oemer). **Screenshot é caso à parte e é
  viável** sem OMR: ver pendência 4.
- **Pauta de ritmo (1 linha)** — não tem altura para nomear. É a maior parte do 1,15%
  de cobertura que falta. Poderia ao menos avisar "pauta de ritmo" em vez de silenciar.
- **Clave de fá e de dó** — implementadas, nunca testadas (o caso do Manuel é sax).
- **Acorde na partitura** (várias cabeças no mesmo x) — empilha os nomes, pouco testado.

---

## 9. Ideias maiores (não são pendência, são direção)

1. **Seguidor de partitura pelo microfone** — detectar a altura tocada e andar um cursor
   pelo PDF, marcando onde parou e o que saiu errado. Só é possível porque sei a
   coordenada de cada nota na página.
2. **Dedilhado em vez de nome** — desenhar o diagrama de chaves do sax embaixo da nota,
   pulando a tradução "nome → dedo". Mesma máquina, muda só o que é estampado.
3. **Caderno de treino** — recortar do PDF original os compassos mais difíceis e montar
   uma folha de exercícios. Com a ideia 1, o corte passa a ser pelo que você errou de
   fato, não pela minha estimativa.
