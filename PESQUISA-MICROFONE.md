# Seguidor de partitura pelo microfone

Estudo de viabilidade — 2026-08-01. Pergunta: o navegador ouvir o sax e **rolar a partitura
sozinho**, acompanhando onde a pessoa está tocando.

## Veredito

**Viável, e mais fácil aqui do que em qualquer app de partitura** — por um motivo que não
tem a ver com áudio: eu já sei a **coordenada de cada nota na página**. O trabalho pesado de
um seguidor comercial é descobrir onde a nota está desenhada; aqui isso é dado de entrada.

O que falta é a metade de áudio, e ela se divide em duas partes de dificuldade bem
diferente:

| Parte | Dificuldade | Por quê |
|---|---|---|
| **detectar a altura** que está soando | baixa | sax é monofônico e tem harmônico forte; é o caso mais fácil de detecção de altura |
| **casar isso com a partitura** | média | a pessoa erra, repete, para no meio e recomeça — e o seguidor não pode se perder |

## Por que o sax é o caso fácil

Detectar altura de piano ou violão é difícil porque soam **várias notas juntas**. Sax toca
uma nota por vez: o sinal é quase periódico, e achar o período é achar a nota. Autocorrelação
resolve — é o que o YIN faz, e ele roda de sobra em tempo real no navegador.

A conta: sax alto escrito vai de Bb3 a F#6, que **soando** é Db3 (≈139 Hz) a A5 (≈880 Hz).
Com 44,1 kHz, um período de 139 Hz tem ~317 amostras; uma janela de 2048 amostras (46 ms)
pega seis períodos inteiros, folgado. A resolução em cents é boa o suficiente para separar
semitons com margem enorme — e semitom é tudo o que preciso, não afinação fina.

**Latência esperada:** 46 ms de janela + ~20 ms de hop + o buffer de entrada do sistema
(~10–25 ms) = da ordem de **80 ms**. Isso é abaixo do que se percebe como atraso num scroll,
e muito abaixo da duração de qualquer nota real.

## O que já está pronto do lado da partitura

Três coisas que este projeto tem e um app genérico não:

1. **`ler_notas` dá `x`, `y_base`, `sistema`, `pagina` de cada cabeça** — o scroll é só levar
   a linha do sistema atual para o meio da tela. Nem preciso de renderização nova: a prévia
   já é a página em pontos de PDF e o editor já converte ponto ↔ pixel (`getScreenCTM`).
2. **`melodia()` já dá a sequência tocável** `[{t, midi, d}]` na ordem de leitura, com o
   índice do sistema em cada evento. Isso é exatamente a "partitura de referência" que um
   seguidor precisa.
3. **A altura lida é MIDI escrito.** O microfone ouve o som **real**, uma sexta maior abaixo
   (`TRANSPOSICAO_ALTO = -9`). Comparar sem transpor faria o seguidor errar por 9 semitons em
   toda nota — é a armadilha número um desta feature.

## Como casar áudio com partitura

Três desenhos possíveis, do mais simples ao mais robusto:

### A. Janela deslizante de expectativa (recomendado para começar)

Guardo um cursor. A cada nota detectada, comparo com as próximas ~8 notas esperadas:

- bate com a próxima → anda 1
- bate com uma das seguintes → pula para lá (a pessoa cortou ou eu perdi uma)
- não bate com nenhuma → **não faço nada** (nota errada, ruído, respiração)

Só rolo a tela quando o cursor troca de sistema. Umas 60 linhas de JS, sem biblioteca, e o
comportamento é previsível — que é o que importa num atril: um seguidor que pula sozinho para
o lugar errado é pior que nenhum.

O ponto delicado é **repetição**: numa escala com muitos D seguidos, "bateu com a próxima" é
ambíguo. Duas travas resolvem: exigir mudança de altura para andar (ataque de nota repetida
não conta) e exigir que a nota se sustente por 2 janelas antes de valer.

### B. Alinhamento temporal (DTW online)

O jeito acadêmico: casar a sequência tocada com a esperada permitindo esticar e encolher o
tempo. Mais robusto a andamento livre e a notas erradas, e é o que os seguidores de verdade
usam. Custa mais código e um estado maior — e para um estudo pessoal, resolve um problema que
o A já resolve na prática.

### C. Só ritmo, sem altura

Detectar apenas **ataque** (onset) e andar no relógio. Muito mais simples, mas se perde
exatamente onde mais dói: quando a pessoa para para respirar ou repete um trecho.

## O que a plataforma exige

- `getUserMedia({audio: true})` pede **permissão do usuário**, e o Chrome só concede em
  **HTTPS** — o GitHub Pages já é HTTPS, então não muda nada no deploy.
- Desligar `echoCancellation`, `noiseSuppression` e `autoGainControl`. São feitos para voz em
  chamada, e destroem justamente a parte harmônica do sax.
- `AudioWorklet` para a análise (thread de áudio própria). `ScriptProcessor` é obsoleto e
  gagueja quando o Pyodide está trabalhando na thread principal.
- O detector é **JS puro, não Python**: precisa rodar a cada 20 ms, e não faz sentido
  atravessar o Pyodide para isso. A partitura de referência vem do Python uma vez só.

## Riscos honestos

1. **Ruído e realimentação.** Se o acompanhamento (play-along, já no ar) estiver tocando no
   alto-falante, o microfone ouve o acorde e pode confundi-lo com a nota tocada. Mitigação:
   ignorar altura que coincida com o que estou sintetizando naquele instante — eu sei
   exatamente o que estou tocando, o que um app comum não sabe.
2. **Oitava errada.** Autocorrelação erra oitava com facilidade (pega o subharmônico). Como
   só preciso da classe de altura para casar, um erro de oitava é absorvível — mas tem de ser
   decisão explícita, não acidente.
3. **A pessoa improvisando.** No solo, o que ela toca não está escrito. O seguidor precisa de
   um estado "perdi, mas não vou pular" e de um jeito de voltar (a cifra da linha, que eu já
   leio, dá uma âncora grosseira).
4. **Celular no atril.** É o caso de uso real, e é onde a bateria e o Safari mais reclamam.
   Não testado — mesma pendência do resto do app.

## Esforço estimado

- detector de altura em AudioWorklet (autocorrelação + trava de estabilidade): **meio dia**
- casador A + cursor + scroll suave por sistema: **meio dia**
- afinar em cima de gravação real do Manuel tocando: **o resto do tempo** — e é a parte que
  decide se presta, porque calibrar isso no sintetizador engana (ataque limpo, afinação
  perfeita, sem respiração).

**Pré-requisito de teste:** uma gravação sua tocando uma das partituras do acervo, com o
celular, no volume normal. Sem isso, qualquer número que eu reporte é sobre o meu próprio
sintetizador, o que já deu errado antes neste projeto (ver o padrão anotado no `CLAUDE.md`).
