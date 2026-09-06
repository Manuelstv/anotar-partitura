"""HTML autocontido, editavel e tocavel, gerado de um PDF de partitura.

Molde: um arquivo por musica, que abre sozinho, toca e acompanha destacando a nota.
A diferenca para os players do genero (Verovio + MusicXML) e que aqui NADA e
re-engravado: a pagina e a imagem do PDF do arranjador, e o destaque e desenhado por
cima usando as coordenadas que o nucleo ja le. O som sai sintetizado do proprio
midi/duracao — sem MP3, e sem timemap que possa dessincronizar do audio.

Uso: PYTHONPATH=<repo> python3 gerar_html.py <entrada.pdf> <saida.html>
"""
import base64, html, json, sys
import anotar_partitura as A

CSS = """
:root {
  --tinta: #16171b; --tinta-2: #55534d; --tinta-3: #86837b;
  --fundo: #f2efe9; --superficie: #fbfaf7; --borda: #dcd8cf;
  --realce: #b0442b;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --tinta: #e8e5de; --tinta-2: #a39f96; --tinta-3: #7c7871;
    --fundo: #17181b; --superficie: #1e2024; --borda: #32333a;
    --realce: #e07b5e;
  }
}
:root[data-theme="dark"] {
  --tinta: #e8e5de; --tinta-2: #a39f96; --tinta-3: #7c7871;
  --fundo: #17181b; --superficie: #1e2024; --borda: #32333a;
  --realce: #e07b5e;
}
* { box-sizing: border-box; }
body { background: var(--fundo); color: var(--tinta);
  font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, sans-serif; }
.folha { max-width: 960px; margin: 0 auto; padding: 28px 20px 80px;
  display: flex; flex-direction: column; gap: 24px; }
h1 { margin: 0; font-family: Spectral, Georgia, "Times New Roman", serif;
  font-size: 27px; font-weight: 600; letter-spacing: -.01em; text-wrap: balance; }
.selo { font-size: 11px; text-transform: uppercase; letter-spacing: .09em;
  color: var(--realce); font-weight: 600; }
header { display: flex; flex-direction: column; gap: 7px; }
.resumo { margin: 0; display: flex; flex-wrap: wrap; gap: 4px 18px;
  font-size: 13px; color: var(--tinta-2); font-variant-numeric: tabular-nums; }
.resumo b { color: var(--tinta); font-weight: 600; }

/* O transporte gruda no topo: com varias paginas, rolar nao pode tirar o Tocar da tela */
.transporte { position: sticky; top: 0; z-index: 8; display: flex; flex-wrap: wrap;
  align-items: center; gap: 10px 14px; padding: 11px 14px;
  background: var(--superficie); border: 1px solid var(--borda); border-radius: 8px;
  box-shadow: 0 2px 10px rgba(0,0,0,.07); }
button { font: inherit; font-size: 13px; padding: 7px 13px; cursor: pointer;
  color: var(--tinta); background: var(--superficie);
  border: 1px solid var(--borda); border-radius: 5px; }
button:hover:not(:disabled) { border-color: var(--tinta-3); }
button:disabled { opacity: .45; cursor: default; }
button:focus-visible, input:focus-visible { outline: 2px solid var(--realce);
  outline-offset: 2px; }
button[data-play] { min-width: 106px; font-weight: 600; }
button[aria-pressed="true"][data-modo] { background: var(--realce);
  border-color: var(--realce); color: #fff; }
.barra-edicao { display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
  padding: 9px 14px; border: 1px dashed var(--realce); border-radius: 8px;
  background: color-mix(in srgb, var(--realce) 6%, transparent); }
.barra-edicao[hidden] { display: none; }
.medidor { font-size: 12.5px; color: var(--tinta-2); min-width: 9ch;
  font-variant-numeric: tabular-nums; }
input[type=range] { accent-color: var(--realce); }
input[data-seek] { flex: 1 1 200px; min-width: 140px; }
.andamento { display: flex; align-items: center; gap: 7px; font-size: 12.5px;
  color: var(--tinta-2); }
.andamento input { width: 96px; }
.andamento span { min-width: 7ch; font-variant-numeric: tabular-nums; }
.linha-2 { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.dica { margin: 0; font-size: 12.5px; color: var(--tinta-3); }
.dica kbd { font: inherit; font-size: 11.5px; border: 1px solid var(--borda);
  border-radius: 3px; padding: 1px 5px; background: var(--superficie); }

/* A partitura e papel: fica branca nos DOIS temas. Inverter deixaria a pauta ilegivel —
   o PNG e preto sobre branco e nao acompanha token nenhum. */
.pg { margin: 0; }
.papel { position: relative; background: #fff; border: 1px solid var(--borda);
  box-shadow: 0 1px 3px rgba(0,0,0,.14); overflow: hidden; cursor: pointer; }
.papel img { display: block; width: 100%; height: auto; }
.papel svg { position: absolute; inset: 0; width: 100%; height: 100%; }
.papel svg.nomes text { fill: #1b3fa0; font-family: Helvetica, Arial, sans-serif; }
/* a camada do destaque nao intercepta clique: quem recebe e o papel, sempre */
.papel svg.seguidor { pointer-events: none; }
.papel svg.seguidor .marca { fill: rgba(176,68,43,.17);
  stroke: rgba(176,68,43,.55); stroke-width: .7; rx: 2; }
.editando .papel { cursor: crosshair; }
.editando .papel svg.nomes .toque { fill: transparent; cursor: pointer; }
.editando .papel svg.nomes g:hover text { fill: #b0442b; font-weight: 700; }
.editando .papel svg.nomes g.sel text { fill: #b0442b; font-weight: 700; }
.editando .papel svg.nomes g.sel .toque { fill: rgba(176,68,43,.14); }
.campo-edit { position: absolute; z-index: 5; width: 4.6rem; padding: 3px 5px;
  font: inherit; font-size: 13px; text-align: center; color: #16171b;
  background: #fff; border: 2px solid #b0442b; border-radius: 4px; }
figcaption { margin-top: 7px; font-size: 12px; color: var(--tinta-3);
  display: flex; justify-content: space-between; gap: 12px;
  font-variant-numeric: tabular-nums; }
.nota-rodape { font-size: 13px; color: var(--tinta-2);
  border-top: 1px solid var(--borda); padding-top: 16px; max-width: 64ch; }
.nota-rodape code { font-size: 12px; padding: 1px 5px; border-radius: 3px;
  background: color-mix(in srgb, var(--tinta) 8%, transparent); }
@media (prefers-reduced-motion: reduce) { * { scroll-behavior: auto !important; } }
"""


def _lado(arq):
    """Le um irmao deste .py. No Pyodide tudo mora em /, no CLI mora ao lado."""
    import os
    aqui = os.path.dirname(os.path.abspath(__file__))
    for c in (os.path.join(aqui, arq), "/" + arq):
        if os.path.exists(c):
            return open(c, encoding="utf-8").read()
    raise FileNotFoundError(arq)


def html_de(dados, nome="partitura.pdf", bpm=90, rotulos_prontos=None):
    """Devolve o HTML como str.

    `rotulos_prontos` e a lista do editor do site: quando vem, o HTML sai com as
    correcoes que o Manuel ja fez na tela, e nao com a leitura crua.
    """
    _, rel = A.anotar_bytes(dados, saida="pdf", estampar=False)
    paginas = rel["paginas"]

    try:
        mel = A.melodia(dados)
    except Exception as e:                      # sem ritmo o resto ainda serve
        print("  aviso: melodia falhou (%s) — sai sem player" % e)
        mel = {"notas": [], "total": 0, "sistemas": [], "compassos": []}

    nome_curto = nome.rsplit(".", 1)[0]
    crus = rotulos_prontos if rotulos_prontos is not None else rel["rotulos"]
    rotulos = [
        {"id": "r%d" % i, "pagina": r["pagina"], "x": round(r["x"], 2),
         "y_base": round(r["y_base"], 2), "corpo": round(r.get("corpo") or 8, 2),
         "texto": r["texto"]}
        for i, r in enumerate(crus) if r.get("texto")
    ]
    notas = [{"t": round(n["t"], 4), "midi": n["midi"], "d": round(n["d"], 4),
              "pg": n["pg"], "sl": n["sl"], "x": round(n["x"], 2)}
             for n in mel["notas"]]

    seg = int(round((mel["total"] or 0) * 60 / bpm))
    fmt_dur = f"{seg // 60}:{seg % 60:02d} a {bpm} bpm" if seg else "sem ritmo lido"

    partes = []
    for i, pg in enumerate(paginas):
        png, _m = A.previa_de(dados, i)
        b64 = base64.b64encode(png).decode()
        vb = f'0 0 {pg["largura"]} {pg["altura"]}'
        partes.append(
            f'<figure class="pg">\n<div class="papel" data-pg="{i}">\n'
            f'<img src="data:image/png;base64,{b64}" alt="Pagina {i + 1} da partitura">\n'
            f'<svg class="seguidor" viewBox="{vb}" aria-hidden="true"></svg>\n'
            f'<svg class="nomes" viewBox="{vb}"></svg>\n'
            f'</div>\n<figcaption><span>Pagina {i + 1} de {len(paginas)}</span>'
            f'<span data-conta></span></figcaption>\n</figure>')

    doc_js = json.dumps({"arquivo": nome, "rotulos": rotulos, "notas": notas,
                         "sistemas": mel["sistemas"], "total": mel["total"]},
                        ensure_ascii=False, separators=(",", ":"))
    js_sax = _lado("sax.js")
    js_player = _lado("player_js.js")

    # Cabecalho de documento COMPLETO: este arquivo abre sozinho, sem servidor e sem
    # ninguem para embrulhar. Sem o charset, ▶ e ⏸ e todo acento saem como "â¸" — e
    # sem o viewport, a partitura abre minúscula no celular.
    doc = f"""<!doctype html>
<html lang="pt-BR">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(nome_curto)} — partitura</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Spectral:wght@600&display=swap">
<style>{CSS}</style>
<div class="folha">
<header>
  <span class="selo">O PDF original, com nome de nota e player por cima</span>
  <h1>{html.escape(nome)}</h1>
  <p class="resumo"><span><b>{len(paginas)}</b> {"pagina" if len(paginas) == 1 else "paginas"}</span>
    <span><b>{len(notas)}</b> notas</span>
    <span>{fmt_dur}</span></p>
</header>

<div class="transporte">
  <button type="button" data-play aria-pressed="false">&#9654; Tocar</button>
  <input type="range" data-seek min="0" max="1000" value="0" step="1"
         aria-label="Posicao na musica">
  <span class="medidor" data-relogio>0:00 / 0:00</span>
  <label class="andamento">Andamento
    <input type="range" data-bpm min="30" max="200" value="{bpm}" step="1">
    <span data-bpmval>{bpm} bpm</span></label>
  <button type="button" data-modo aria-pressed="false">Corrigir nomes</button>
</div>
<div class="barra-edicao" hidden>
  <button type="button" data-desfazer disabled>Desfazer</button>
  <button type="button" data-copiar disabled>Copiar correções</button>
  <button type="button" data-limpar disabled>Voltar ao lido</button>
</div>
<p class="dica" data-dica>Clique numa nota para pular para ela.</p>

{"".join(partes)}

<p class="nota-rodape">Cada pagina e a imagem do PDF original, intacta: os nomes e o
destaque do player sao SVG posicionado em pontos do PDF por cima dela. Nada foi
re-engravado. O som e sintetizado das proprias alturas e duracoes lidas do arquivo, entao
o destaque nao tem como sair de sincronia com o audio. Este arquivo nao carrega Pyodide,
entao ele nao gera PDF: as correcoes ficam guardadas neste navegador e saem em JSON por
<code>Copiar correções</code>.</p>
</div>
<script>{js_sax}</script>
<script>const DOC={doc_js};</script>
<script>{js_player}</script>
"""
    return doc


def gerar(caminho_pdf, saida, bpm=90):
    """Atalho de linha de comando: le o PDF, grava o .html."""
    import os
    dados = open(caminho_pdf, "rb").read()
    doc = html_de(dados, os.path.basename(caminho_pdf), bpm)
    with open(saida, "w", encoding="utf-8") as f:
        f.write(doc)
    return doc


if __name__ == "__main__":
    doc = gerar(sys.argv[1], sys.argv[2])
    print("%s: %.0f KB" % (sys.argv[2], len(doc) / 1024))
