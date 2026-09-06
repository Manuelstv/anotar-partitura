(() => {
  const svgNS = "http://www.w3.org/2000/svg";
  const CHAVE = "partitura:" + DOC.arquivo;

  // ------------------------------------------------------------------ nomes
  let rotulos = DOC.rotulos.map(r => ({ ...r }));
  try {
    const salvo = localStorage.getItem(CHAVE);
    if (salvo) {
      const m = new Map(JSON.parse(salvo).map(r => [r.id, r]));
      rotulos = rotulos.map(r => (m.has(r.id) ? { ...r, ...m.get(r.id) } : r));
      for (const r of m.values()) if (!rotulos.some(x => x.id === r.id)) rotulos.push(r);
    }
  } catch (e) {}
  const guardarDisco = () => {
    try { localStorage.setItem(CHAVE, JSON.stringify(rotulos)); } catch (e) {}
  };

  const pilha = [];
  const guardar = () => {
    pilha.push(rotulos.map(r => ({ ...r })));
    if (pilha.length > 50) pilha.shift();
  };
  let editando = false, sel = null, campo = null, proximoId = rotulos.length;

  const q = s => document.querySelector(s);
  const btModo = q("[data-modo]"), btDesf = q("[data-desfazer]");
  const btCopiar = q("[data-copiar]"), btLimpar = q("[data-limpar]");
  const palcos = [...document.querySelectorAll(".papel")];

  const soltarCampo = (aplicar) => {
    const c = campo;
    if (!c) return;
    campo = null;                    // ANTES de remover: remover dispara blur, e o blur
    c.remove();                      // chamaria isto de novo, aplicando o que era cancelar
    if (!aplicar) return;
    const r = rotulos.find(x => x.id === c.dataset.id);
    if (!r || c.value.trim() === r.texto) return;
    guardar();
    r.texto = c.value.trim();        // vazio apaga: o <text> deixa de ser desenhado
    guardarDisco();
    desenharNomes();
  };

  function desenharNomes() {
    for (const papel of palcos) {
      const i = +papel.dataset.pg;
      const svg = papel.querySelector("svg.nomes");
      svg.textContent = "";
      for (const r of rotulos) {
        if (r.pagina !== i || !r.texto) continue;
        const g = document.createElementNS(svgNS, "g");
        if (sel === r.id) g.setAttribute("class", "sel");
        const t = document.createElementNS(svgNS, "text");
        t.setAttribute("x", r.x); t.setAttribute("y", r.y_base);
        t.setAttribute("font-size", r.corpo);
        t.setAttribute("text-anchor", "middle");
        t.textContent = r.texto;
        // alvo de toque generoso: o glifo tem ~4pt de largura e dedo nao acerta
        const toque = document.createElementNS(svgNS, "rect");
        toque.setAttribute("class", "toque");
        toque.setAttribute("x", r.x - r.corpo);
        toque.setAttribute("y", r.y_base - r.corpo);
        toque.setAttribute("width", r.corpo * 2);
        toque.setAttribute("height", r.corpo * 1.35);
        toque.dataset.id = r.id;
        g.append(t, toque);
        svg.append(g);
      }
      const cap = papel.parentElement.querySelector("[data-conta]");
      if (cap) cap.textContent =
        rotulos.filter(r => r.pagina === i && r.texto).length + " nomes";
    }
    const mudados = rotulos.filter(r => {
      const o = DOC.rotulos.find(x => x.id === r.id);
      return !o || o.texto !== r.texto;
    }).length;
    btCopiar.disabled = btLimpar.disabled = mudados === 0;
    btCopiar.textContent = mudados
      ? "Copiar " + mudados + (mudados === 1 ? " correção" : " correções")
      : "Copiar correções";
    btDesf.disabled = pilha.length === 0;
  }

  const abrirCampo = (papel, r) => {
    soltarCampo(false);
    sel = r.id;
    desenharNomes();
    const svg = papel.querySelector("svg.nomes");
    const pr = papel.getBoundingClientRect();
    const tela = new DOMPoint(r.x, r.y_base).matrixTransform(svg.getScreenCTM());
    campo = document.createElement("input");
    campo.className = "campo-edit";
    campo.value = r.texto;
    campo.dataset.id = r.id;
    campo.title = "Enter aplica, vazio apaga, Esc cancela";
    campo.style.left = Math.max(2, Math.min(pr.width - 78, tela.x - pr.left - 37)) + "px";
    campo.style.top = Math.min(pr.height - 30, tela.y - pr.top + 5) + "px";
    campo.addEventListener("keydown", ev => {
      if (ev.key === "Enter") { ev.preventDefault(); soltarCampo(true); }
      if (ev.key === "Escape") { ev.preventDefault(); soltarCampo(false); }
    });
    campo.addEventListener("blur", () => soltarCampo(true));
    papel.append(campo);
    campo.focus(); campo.select();
  };

  for (const papel of palcos) {
    papel.addEventListener("click", ev => {
      if (!editando) return;
      const alvo = ev.target.closest(".toque");
      if (alvo) {
        const r = rotulos.find(x => x.id === alvo.dataset.id);
        if (r) abrirCampo(papel, r);
        return;
      }
      if (campo) { soltarCampo(true); return; }
      const svg = papel.querySelector("svg.nomes");
      const p = new DOMPoint(ev.clientX, ev.clientY)
        .matrixTransform(svg.getScreenCTM().inverse());
      const corpo = rotulos.find(r => r.pagina === +papel.dataset.pg)?.corpo || 8;
      guardar();
      const novo = { id: "n" + (proximoId++), pagina: +papel.dataset.pg,
                     x: p.x, y_base: p.y, corpo, texto: "" };
      rotulos.push(novo);
      abrirCampo(papel, novo);
    });
  }

  // Os controles de edicao so existem no modo edicao: fora dele a barra tinha seis
  // botoes de duas tarefas diferentes lado a lado, e nao dava para ver o que era o quê.
  const faixaEdicao = q(".barra-edicao"), dica = q("[data-dica]");
  const DICA_TOCAR = "Clique numa nota para pular para ela.";
  const DICA_EDITAR = "Clique num nome para trocar, no vazio para acrescentar. "
    + "Enter aplica, campo vazio apaga, Esc cancela, Ctrl+Z desfaz.";
  btModo.addEventListener("click", () => {
    editando = !editando;
    soltarCampo(false); sel = null;
    btModo.setAttribute("aria-pressed", String(editando));
    btModo.textContent = editando ? "Terminar correção" : "Corrigir nomes";
    faixaEdicao.hidden = !editando;
    dica.textContent = editando ? DICA_EDITAR : DICA_TOCAR;
    document.querySelector(".folha").classList.toggle("editando", editando);
    desenharNomes();
  });
  const desfazer = () => {
    if (!pilha.length) return;
    soltarCampo(false);
    rotulos = pilha.pop();
    guardarDisco(); desenharNomes();
  };
  btDesf.addEventListener("click", desfazer);
  addEventListener("keydown", ev => {
    if ((ev.ctrlKey || ev.metaKey) && ev.key === "z") { ev.preventDefault(); desfazer(); }
  });
  btCopiar.addEventListener("click", async () => {
    const mudados = rotulos.filter(r => {
      const o = DOC.rotulos.find(x => x.id === r.id);
      return !o || o.texto !== r.texto;
    });
    try {
      await navigator.clipboard.writeText(
        JSON.stringify({ arquivo: DOC.arquivo, correcoes: mudados }, null, 2));
      btCopiar.textContent = "Copiado";
    } catch (e) { btCopiar.textContent = "Não deu para copiar"; }
    setTimeout(desenharNomes, 1500);
  });
  btLimpar.addEventListener("click", () => {
    guardar();
    rotulos = DOC.rotulos.map(r => ({ ...r }));
    try { localStorage.removeItem(CHAVE); } catch (e) {}
    desenharNomes();
  });

  // ----------------------------------------------------------------- player
  // Sem MP3: o som e sintetizado do proprio midi/duracao lidos do PDF, entao o arquivo
  // continua autocontido e a posicao do destaque vem do MESMO dado que gera o audio —
  // nao ha timemap para dessincronizar.
  const notas = DOC.notas;
  const sistemas = new Map(DOC.sistemas.map(s => [s.pg + ":" + s.sl, s]));
  const btPlay = q("[data-play]"), seek = q("[data-seek]"), relogio = q("[data-relogio]");
  const bpmSel = q("[data-bpm]"), bpmVal = q("[data-bpmval]");
  let ac = null, tocando = false, t0 = 0, pos = 0, bpm = +bpmSel.value;
  const totalTempos = DOC.total || (notas.length ? notas.at(-1).t + notas.at(-1).d : 0);
  const segDe = tempos => tempos * 60 / bpm;
  const fmt = s => {
    s = Math.max(0, s || 0);
    return Math.floor(s / 60) + ":" + String(Math.floor(s % 60)).padStart(2, "0");
  };

  // O som sai da MESMA sintese de sax do site (sax.js, embutido acima) — nao de uma onda
  // simples. Web Audio nao deixa desagendar nota, entao calar e derrubar a saida:
  // `cortarSaida` faz exatamente isso.
  const pararSom = () => { try { cortarSaida(); } catch (e) {} };
  const agendar = (desdeTempos) => {
    const base = ac.currentTime + 0.08;
    for (const n of notas) {
      if (n.t + n.d <= desdeTempos) continue;
      const ini = Math.max(n.t, desdeTempos);
      tocarNota(n.midi, base + segDe(ini - desdeTempos),
                segDe(n.t + n.d - ini));
    }
  };

  const destaque = (papel) => {
    let d = papel.querySelector(".marca");
    if (!d) {
      d = document.createElementNS(svgNS, "rect");
      d.setAttribute("class", "marca");
      papel.querySelector("svg.seguidor").append(d);
    }
    return d;
  };
  const esconderMarcas = () => {
    for (const papel of palcos) destaque(papel).style.display = "none";
  };

  const notaEm = (tempos) => {
    let atual = null;
    for (const n of notas) {
      if (n.t <= tempos + 1e-6 && tempos < n.t + n.d) return n;
      if (n.t <= tempos) atual = n;
    }
    return atual;
  };

  let ultimaPg = -1;
  const pintar = (tempos) => {
    const n = notaEm(tempos);
    esconderMarcas();
    if (!n) return;
    const s = sistemas.get(n.pg + ":" + n.sl);
    if (!s) return;
    const papel = palcos.find(p => +p.dataset.pg === n.pg);
    if (!papel) return;
    const seguinte = notas.find(o => o.pg === n.pg && o.sl === n.sl && o.x > n.x);
    const largura = seguinte ? Math.min(seguinte.x - n.x, 46) : 16;
    const d = destaque(papel);
    // a marca cobre a ALTURA DA PAUTA com folga: a nota pode estar em linha suplementar
    d.setAttribute("x", n.x - largura / 2);
    d.setAttribute("width", Math.max(largura, 9));
    d.setAttribute("y", s.topo - 11);
    d.setAttribute("height", (s.base - s.topo) + 22);
    d.style.display = "";
    if (n.pg !== ultimaPg) {
      ultimaPg = n.pg;
      papel.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  const laco = () => {
    if (!tocando) return;
    const tempos = pos + (ac.currentTime - t0) * bpm / 60;
    if (tempos >= totalTempos) { parar(); pos = 0; atualizarBarra(0); return; }
    atualizarBarra(tempos);
    pintar(tempos);
    requestAnimationFrame(laco);
  };
  const atualizarBarra = (tempos) => {
    seek.value = totalTempos ? Math.round(tempos / totalTempos * 1000) : 0;
    relogio.textContent = fmt(segDe(tempos)) + " / " + fmt(segDe(totalTempos));
  };
  const parar = () => {
    if (tocando) pos += (ac.currentTime - t0) * bpm / 60;
    tocando = false;
    pararSom();
    btPlay.textContent = "▶ Tocar";
    btPlay.setAttribute("aria-pressed", "false");
  };
  const tocar = async () => {
    if (!ac) ac = audio();          // de sax.js: cria o contexto, a onda e o sopro
    if (ac.state === "suspended") await ac.resume();
    if (pos >= totalTempos) pos = 0;
    t0 = ac.currentTime;
    tocando = true;
    agendar(pos);
    btPlay.textContent = "⏸ Pausar";
    btPlay.setAttribute("aria-pressed", "true");
    requestAnimationFrame(laco);
  };
  btPlay.addEventListener("click", () => (tocando ? parar() : tocar()));
  seek.addEventListener("input", () => {
    const estava = tocando;
    parar();
    pos = totalTempos * seek.value / 1000;
    atualizarBarra(pos);
    pintar(pos);
    if (estava) tocar();
  });
  bpmSel.addEventListener("input", () => {
    const estava = tocando;
    parar();
    bpm = +bpmSel.value;
    bpmVal.textContent = bpm + " bpm";
    atualizarBarra(pos);
    if (estava) tocar();
  });
  // clique na partitura com o player parado pula para aquele ponto da musica
  for (const papel of palcos) {
    papel.addEventListener("click", ev => {
      if (editando) return;
      const svg = papel.querySelector("svg.nomes");
      const p = new DOMPoint(ev.clientX, ev.clientY)
        .matrixTransform(svg.getScreenCTM().inverse());
      const pg = +papel.dataset.pg;
      let melhor = null, dist = Infinity;
      for (const n of notas) {
        const s = sistemas.get(n.pg + ":" + n.sl);
        if (n.pg !== pg || !s) continue;
        const dy = p.y < s.topo - 24 || p.y > s.base + 24 ? 1e4 : 0;
        const d = Math.abs(n.x - p.x) + dy;
        if (d < dist) { dist = d; melhor = n; }
      }
      if (!melhor || dist > 400) return;
      const estava = tocando;
      parar();
      pos = melhor.t;
      atualizarBarra(pos); pintar(pos);
      if (estava) tocar();
    });
  }

  desenharNomes();
  atualizarBarra(0);
  bpmVal.textContent = bpm + " bpm";
  if (notas.length) pintar(notas[0].t);
})();
