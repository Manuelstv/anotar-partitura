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

## 4. ~~Aceitar IMAGEM além de PDF (print de celular, JPG/PNG)~~ — NO AR

**Requisito (decidido com o Manuel):** os dois formatos, **coexistindo**. Imagem é entrada
de **primeira classe**, não fallback — o tipo é decidido **na porta**, pelo mime/extensão,
nunca por fracasso de detecção de vetor. Fallback silencioso faz um PDF ruim ser lido como
imagem e ninguém entende por quê. Saída: **PDF ou imagem, com botão de escolha**,
independente do formato de entrada.

**Implementado e no ar.** `bitmap.py` (novo) + `templates_bitmap.json` (banco de 89 KB) +
ramo de imagem no `anotar_bytes()`. As quatro combinações entrada×saída funcionam, na CLI
e no site.

Medido pelo caminho de PRODUÇÃO (`_exploracao/validar_bitmap.py`, 6 arquivos, 780 notas,
gabarito = leitura vetorial do mesmo arquivo):

| entrada | cabeças | grau | nome | falso positivo |
|---|---|---|---|---|
| PNG limpo | **99,2%** | **100%** | **98,1%** | 2,1% |
| JPEG q60 | 94,1% | **100%** | 96,7% | 1,8% |

Confirmado no navegador: `cv2 4.11.0` importa no Pyodide 0.28.3 (3,7 s de download +
0,75 s de import) e `matchTemplate`, `connectedComponentsWithStats`, `findContours`,
`morphologyEx`, `resize` e `floodFill` todos funcionam.

**Zero regressão no modo vetor**: 14 casos comparados contra a versão publicada anterior,
mesma contagem de sistemas e de rótulos em todos, `Song_of_somg` mantendo o `E#` da 1ª
nota. E quem manda PDF **não baixa o opencv** — verificado interceptando o `fetch`.

O que ainda falta:

1. **Testar com print de celular DE VERDADE.** Tudo acima usa PDF renderizado como se
   fosse print. Print real tem subpixel rendering da tela, escala fracionária, barra de
   status e recorte — nada disso está coberto. **Depende de o Manuel mandar 2–3 prints.**
2. **Armadura de bemol no Strasbourg**: 8 notas saem `B` em vez de `Bb` — a armadura de
   1 bemol não é detectada naquele arquivo (nome 93,3%). Erro oposto ao da armadura
   fantasma, e ainda não diagnosticado.
3. **Alteração em imagem: 98,1%** no total, contra 100% no vetor. O grau nunca erra, só a
   alteração. Os arquivos que ainda erram são Strasbourg (93,3%), The-chicken (94,7%) e
   cadernin (95,9%).
4. **Ritmo em imagem** — `beams` volta vazio, então o `_` de nota longa e o player de piano
   não valem no modo imagem.
5. **PDF de várias páginas com saída em imagem** entrega só a 1ª página (a interface avisa).
   Zip ficou de fora.

**Ganho de graça:** com o ramo de bitmap pronto, **PDF escaneado passa a funcionar** —
rasteriza e entra pelo mesmo caminho. Scan costuma vir em 150–300 dpi, o que dá 20+ px por
espaço de pauta, folgado sobre o piso de 10. Deixa de ser limite permanente (ver seção 8).

Limites do modo, por desenho (não são pendência):

- **Exige ~10 px por espaço de pauta** (A4 inteiro com largura ≥ ~1100 px). Com 6 px o
  recall cai para 44%. O `bitmap.ESP_MINIMO` corta em 5 px e a interface avisa.
- **A `analise.py` não existe em imagem** — cifra, tom, escala sugerida, dificuldade e
  `--limpar` dependem de span de texto, que um bitmap não tem. `rel["tem_analise"]` diz
  isso à interface, que mostra o aviso.
- **Foto de papel continua fora.** Perspectiva e sombra são outro problema; o que está
  implementado é screenshot, que não tem nenhum dos dois.

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
