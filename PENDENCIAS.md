# Pendências

Lista viva do que ficou por fazer. Ordem = prioridade.

---

## 1. Nota ligada / nota longa deve receber UM nome só, com `_`

**Hoje:** uma nota sustentada por ligadura recebe o nome repetido em cada cabeça.
No The-chicken sai `G G G`; o certo é `G_`.

**Por quê:** o nome repetido sugere três ataques, quando é um som só. Além de poluir,
ensina errado — o aluno lê três notas.

**Como deve ficar:** o nome aparece na primeira cabeça, seguido de `_` para indicar que
o som continua. As cabeças seguintes da mesma ligadura não recebem nome. É o padrão do
Sibelius no próprio The-chicken, que usa traço de extensão.

**Destravou:** a duração já é lida (item 2, resolvido), então a metade "nota longa sem
ligadura" (mínima, semibreve) é imediata — basta `dur >= 2` para estampar `_`.

**Falta a ligadura de valor.** Caminho provável: ligadura é um caminho **curvo** (Bézier)
ligando duas cabeças de **mesma altura** e adjacentes. Já coleto os desenhos em
`coletar()`, e no MuseScore ela aparece como path preenchido com exatamente 2 itens `c`
(medido na negra: 22 desses na página). Então falta:

1. filtrar arcos curvos de largura compatível, entre duas cabeças vizinhas;
2. se as duas cabeças tiverem a mesma altura → é **ligadura de valor**: suprimir o nome
   da segunda, marcar a primeira com `_` e somar as durações;
3. se tiverem alturas diferentes → é **fraseado**: não mexer nos nomes.

Cuidado: ligadura pode atravessar a barra de compasso e o fim do sistema (a segunda
cabeça está na linha de baixo).

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

## 4. Estimar o acorde de cada compasso quando não há cifra

Hoje, sem cifra, mostro o **campo harmônico** do tom (o que cabe). O passo seguinte é
casar as notas de cada compasso contra os sete graus e sugerir qual acorde soa —
continua determinístico, mas é **palpite** e tem de ser rotulado como tal na interface,
separado do que foi lido.

---

## 5. Forma (A / B / refrão) não aparece na interface

`analise.forma()` já existe e agrupa compassos com a mesma sequência de alturas, mas o
resultado não é exibido. Falta decidir a apresentação (uma faixa tipo `AABA`?) e tratar
repetição aproximada — hoje só casa sequência idêntica.

---

## 6. Testar no iPhone de verdade

Layout conferido em 390px: sem rolagem horizontal. Falta testar no aparelho:

- **memória** — o Safari mata aba pesada; Pyodide + PyMuPDF pede centenas de MB.
  Partitura curta deve ir; o cadernin de 253 páginas provavelmente derruba.
- **download** — `download` de arquivo gerado em memória é instável no Safari; pode
  abrir o PDF em vez de salvar. Se acontecer, oferecer um botão "abrir" alternativo.
- **áudio** — o player só cria o `AudioContext` no clique, que é o que o iOS exige.
  Não testado em aparelho.

---

## 7. Casos não cobertos (conhecidos, não são bugs)

- **PDF escaneado** — sem vetor não há coordenada. Precisaria de OMR (Audiveris/oemer).
- **Pauta de ritmo (1 linha)** — não tem altura para nomear. É a maior parte do 1,15%
  de cobertura que falta. Poderia ao menos avisar "pauta de ritmo" em vez de silenciar.
- **Clave de fá e de dó** — implementadas, nunca testadas (o caso do Manuel é sax).
- **Acorde na partitura** (várias cabeças no mesmo x) — empilha os nomes, pouco testado.

---

## 8. Ideias maiores (não são pendência, são direção)

1. **Seguidor de partitura pelo microfone** — detectar a altura tocada e andar um cursor
   pelo PDF, marcando onde parou e o que saiu errado. Só é possível porque sei a
   coordenada de cada nota na página.
2. **Dedilhado em vez de nome** — desenhar o diagrama de chaves do sax embaixo da nota,
   pulando a tradução "nome → dedo". Mesma máquina, muda só o que é estampado.
3. **Caderno de treino** — recortar do PDF original os compassos mais difíceis e montar
   uma folha de exercícios. Com a ideia 1, o corte passa a ser pelo que você errou de
   fato, não pela minha estimativa.
