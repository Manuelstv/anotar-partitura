// SINTESE DE SAX ALTO — arquivo unico, usado em dois lugares:
//   1. o site (index.html) carrega por <script src>, ANTES do modulo. Como aqui as
//      funcoes vao para o `window`, o modulo as enxerga pelo escopo global e nenhuma
//      chamada precisou mudar;
//   2. o HTML gerado por player_html.py embute o TEXTO deste arquivo inline, porque
//      aquele arquivo tem de abrir sozinho, sem servidor e sem irmao ao lado.
// Manter uma copia so importa: sao ~170 linhas de timbre calibrado de ouvido, e duas
// copias divergem na primeira correcao que alguem fizer num lado.

let ctxAudio = null, ondaSax = null, bufSopro = null, saidaAudio = null;
function audio() {
  if (ctxAudio) return ctxAudio;
  ctxAudio = new (window.AudioContext || window.webkitAudioContext)();
  saidaAudio = ctxAudio.createGain();
  saidaAudio.connect(ctxAudio.destination);
  // TIMBRE DE SAX ALTO. O sax e um tubo CONICO com palheta: soam todos os harmonicos
  // (diferente da clarineta, cilindrica, que enfatiza os impares), com 2o e 3o fortes — e
  // dai vem o corpo "encorpado" dele. Aqui isso e uma PeriodicWave; a parte imaginaria
  // espalha as fases, senao a onda fica com um pico duro e soa eletronica.
  const re = [0, 1, .72, .56, .36, .26, .175, .12, .085, .06, .042, .03, .021, .015, .011];
  const im = re.map((a, k) => k % 2 ? a * 0.35 : -a * 0.22);
  ondaSax = ctxAudio.createPeriodicWave(Float32Array.from(re), Float32Array.from(im),
                                       { disableNormalization: false });
  // ruido de SOPRO: 1,5 s em loop. Existe no ataque (o "ch" da palheta pegando) e continua
  // baixinho no sustain, que e o que faz soar soprado em vez de sintetizado.
  bufSopro = ctxAudio.createBuffer(1, Math.floor(ctxAudio.sampleRate * 1.5), ctxAudio.sampleRate);
  const d = bufSopro.getChannelData(0);
  let m = 0;
  for (let i = 0; i < d.length; i++) {          // ruido levemente rosa: menos assobio
    m = 0.82 * m + 0.18 * (Math.random() * 2 - 1);
    d[i] = m * 2.2;
  }
  return ctxAudio;
}

function tocarNota(midi, quando, segundos) {
  const c = audio(), f = 440 * Math.pow(2, (midi - 69) / 12);
  // Sax NAO tem cauda de ressonancia como piano: enquanto sopra soa, quando para cala.
  // Entao a nota dura o que tem de durar, com um release curto.
  const dur = Math.max(segundos, 0.12);
  const rel = 0.085;
  const fim = quando + dur + rel;

  const vol = c.createGain();
  // ataque de PALHETA: ~45 ms, com um leve pico antes de assentar no sustain. Ataque
  // instantaneo soa a orgao; lento demais soa a flauta.
  vol.gain.setValueAtTime(0.0001, quando);
  vol.gain.exponentialRampToValueAtTime(0.26, quando + 0.045);
  vol.gain.exponentialRampToValueAtTime(0.195, quando + Math.min(0.16, dur * 0.5));
  // e o AR ACABANDO: o sustain cede ~9% ate o fim da nota. Numa seminima isso e
  // imperceptivel; numa semibreve e o que separa "alguem soprando" de "orgao ligado".
  vol.gain.linearRampToValueAtTime(0.178, quando + dur);
  vol.gain.exponentialRampToValueAtTime(0.0001, fim);

  const filtro = c.createBiquadFilter();
  filtro.type = "lowpass";
  filtro.Q.value = 1.4;
  // o brilho ENTRA junto com o ar, nao comeca aberto: cutoff sobe no ataque e recua no fim
  // Os limites tem PISO ABSOLUTO, nao so multiplo da nota: com cutoff puramente relativo
  // (f*8) o corte caia sobre o 7o harmonico de um la 440 e o timbre perdia o brilho — medi
  // h7=0,06 e h8=0,02, quando o sax real ainda tem energia ali. Sax alto vive de 3 a 5 kHz.
  // O cutoff assenta em 0,35 s FIXO e fica parado ate o release. Antes ele descia ate
  // `quando + dur`: numa semibreve isso virava uma varredura de 4 s, um "uau" lento que
  // nao existe em sax nenhum. Nota curta nem chega no patamar, e continua igual.
  const assenta = Math.min(quando + 0.35, quando + dur);
  filtro.frequency.setValueAtTime(Math.max(800, f * 2.4), quando);
  filtro.frequency.linearRampToValueAtTime(Math.min(11000, Math.max(4600, f * 11)), quando + 0.07);
  filtro.frequency.linearRampToValueAtTime(Math.min(9000, Math.max(3200, f * 7.5)), assenta);
  filtro.frequency.setValueAtTime(Math.min(9000, Math.max(3200, f * 7.5)), quando + dur);
  filtro.frequency.linearRampToValueAtTime(Math.max(900, f * 3), fim);

  // FORMANTES: dois picos fixos (~700 Hz e ~1650 Hz) somados por cima. E o que da o
  // caracter meio nasal, meio vocal do sax — sem eles o timbre fica generico.
  const mistura = c.createGain();
  mistura.connect(vol).connect(saidaAudio);
  filtro.connect(mistura);
  // O de 700 Hz vai em 0,42 e nao 0,5: com 0,5 ele cai em cima do 3o harmonico de um la
  // grave (660 Hz) e deixava o harmonico mais forte que a fundamental — encorpado virava oco.
  for (const [hz, q, g] of [[700, 3.0, 0.42], [1650, 4.0, 0.34]]) {
    const bp = c.createBiquadFilter();
    bp.type = "bandpass"; bp.frequency.value = hz; bp.Q.value = q;
    const gg = c.createGain(); gg.gain.value = g;
    filtro.connect(bp).connect(gg).connect(mistura);
  }

  // VIBRATO: entra depois do ataque, como um saxofonista faz — vibrato desde o primeiro
  // instante e a marca de sintetizador.
  // A taxa e SORTEADA por nota (5,0-5,6 Hz). Com 5,2 fixo, duas semibreves seguidas
  // vibram identicas e o ouvido pega o padrao — e o que denuncia sintetizador.
  const lfo = c.createOscillator();
  lfo.frequency.value = 5.0 + Math.random() * 0.6;
  const prof = c.createGain();
  prof.gain.setValueAtTime(0.0001, quando);
  prof.gain.setValueAtTime(0.0001, quando + 0.18);
  // sobe em 0,9 s em vez de 0,55: o saxofonista abre o vibrato aos poucos na nota longa
  prof.gain.linearRampToValueAtTime(f * 0.008, Math.min(fim, quando + 0.9));
  lfo.connect(prof);
  lfo.start(quando); lfo.stop(fim);

  // O vibrato de sax mexe no volume junto com a altura — so na altura soa a theremin.
  // Entra pelo mesmo LFO, atrasado igual. O valor e ABSOLUTO e soma no envelope, entao
  // 6% do sustain (0,195) e 0,012, nao 0,06 — com 0,06 medi 107% de ondulacao, a nota
  // longa pulsando de escancarada a quase muda.
  const tremor = c.createGain();
  tremor.gain.setValueAtTime(0.0001, quando);
  tremor.gain.setValueAtTime(0.0001, quando + 0.18);
  tremor.gain.linearRampToValueAtTime(0.012, Math.min(fim, quando + 0.9));
  lfo.connect(tremor);
  tremor.connect(vol.gain);   // soma ao envelope ja agendado

  // UM oscilador so. Havia um segundo desafinado em 1,0029 para dar corpo, e ele era a
  // causa da nota longa soar esquisita: duas vozes desafinadas BATEM. Em la 440 a batida
  // saia em f*0,0029 = 1,28 Hz, e medi 47% de ondulacao no sustain de uma semibreve — um
  // tremolo lento que ninguem pediu, que a nota curta escondia (so da tempo de 1/4 de
  // ciclo) e que ainda acelerava no agudo, por ser razao e nao intervalo fixo. Afinar
  // mais nao resolve: em 1,0008 sobrava 0,35 Hz, um inchaco de +45% no meio da nota.
  // Chorus nao tem lugar em sax solo — o corpo vem da PeriodicWave e dos formantes.
  {
    const o = c.createOscillator();
    o.setPeriodicWave(ondaSax);
    o.frequency.setValueAtTime(f * 0.985, quando);          // a palheta "pega" um pouco
    o.frequency.linearRampToValueAtTime(f, quando + 0.05);  // abaixo e sobe
    prof.connect(o.frequency);
    const g = c.createGain(); g.gain.value = 1.4;   // recompoe o volume das duas vozes
    o.connect(g).connect(filtro);
    o.start(quando); o.stop(fim + 0.02);
  }

  // SOPRO: forte no ataque, baixinho durante a nota inteira
  const ar = c.createBufferSource();
  ar.buffer = bufSopro; ar.loop = true;
  const bp = c.createBiquadFilter();
  bp.type = "bandpass"; bp.frequency.value = Math.min(5000, Math.max(1400, f * 4)); bp.Q.value = 0.8;
  const ga = c.createGain();
  ga.gain.setValueAtTime(0.0001, quando);
  ga.gain.linearRampToValueAtTime(0.055, quando + 0.03);
  ga.gain.linearRampToValueAtTime(0.014, quando + 0.16);
  ga.gain.setValueAtTime(0.014, quando + dur);
  ga.gain.linearRampToValueAtTime(0.0001, fim);
  ar.connect(bp).connect(ga).connect(vol);
  ar.start(quando, Math.random() * 1.2);
  ar.stop(fim + 0.02);
}

// Acompanhamento: onda triangular filtrada, volume baixo e ataque mole. O sax e quem tem
// de ser ouvido — o acorde existe para dar o CHAO da harmonia, e por isso o baixo sai em
// senoide, que ocupa a regiao grave sem embolar as vozes de cima.
function tocarAcorde(midis, quando, segundos) {
  const c = audio();
  const dur = Math.max(segundos, 0.3);
  const fim = quando + dur;
  const vol = c.createGain();
  vol.gain.setValueAtTime(0.0001, quando);
  vol.gain.exponentialRampToValueAtTime(0.06, quando + 0.04);
  vol.gain.exponentialRampToValueAtTime(0.033, quando + Math.min(0.8, dur * 0.5));
  vol.gain.exponentialRampToValueAtTime(0.0001, fim + 0.3);
  const lp = c.createBiquadFilter();
  lp.type = "lowpass";
  lp.frequency.value = 2200;
  lp.Q.value = 0.6;
  midis.forEach((m, k) => {
    const o = c.createOscillator();
    o.type = k === 0 ? "sine" : "triangle";
    o.frequency.value = 440 * Math.pow(2, (m - 69) / 12);
    const g = c.createGain();
    g.gain.value = (k === 0 ? 0.85 : 0.55) / Math.sqrt(midis.length);
    o.connect(g).connect(lp);
    o.start(quando);
    o.stop(fim + 0.35);
  });
  lp.connect(vol).connect(saidaAudio);
}

function cortarSaida() {
  // Derruba a saida e poe outra no lugar: o que ja estava agendado continua rodando,
  // mas desligado do alto-falante. E o unico jeito de calar na hora — Web Audio nao
  // deixa "desagendar" nota. Os osciladores morrem sozinhos no stop() deles.
  if (!saidaAudio) return;
  saidaAudio.disconnect();
  saidaAudio = ctxAudio.createGain();
  saidaAudio.connect(ctxAudio.destination);
}

// e o que o resto do site usa pelo escopo global (ver o comentario do topo)
Object.assign(window, { audio, tocarNota, tocarAcorde, cortarSaida });
