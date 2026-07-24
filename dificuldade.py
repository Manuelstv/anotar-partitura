#!/usr/bin/env python3
"""Da uma nota de 0 a 10 para a dificuldade de tocar a partitura no SAX ALTO.

O que e medido (tudo em altura ESCRITA, que e o que o saxofonista le):

  registro   - alcance escrito normal do alto vai de Sib3 (58) a Fa#6 (90).
               Acima disso e altissimo (harmonico, dificil). O extremo agudo usa as
               chaves de palma e o extremo grave as de mindinho: os dois pesam.
  densidade  - notas por compasso. Proxy de velocidade: nao leio duracao, mas mais
               notas no mesmo compasso significa figura mais curta.
  cromatismo - fracao de notas alteradas e quantas classes de altura diferentes
               aparecem. Dedilhado cromatico no sax e mais caro que diatonico.
  saltos     - intervalo medio e maximo entre notas seguidas.
  registro'  - quantas vezes cruza a quebra de oitava Do#5 <-> Re5, que exige a
               chave de oitava e e onde todo mundo trava.

Os PESOS NAO SAO CHUTADOS: sao ajustados por minimos quadrados contra os rotulos
"Beginner / Intermediate / Advanced" que vem no nome dos arquivos do acervo do Manuel
(242 partituras de sax alto rotuladas). O ajuste e a validacao saem no relatorio.

Uso:
    uv run dificuldade.py calibrar <raiz_do_acervo>      # ajusta e valida os pesos
    uv run dificuldade.py nota <pdf> [<pdf> ...]        # da a nota
    uv run dificuldade.py paginas <pdf>                 # uma nota por pagina (caderno)
"""
import glob
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pymupdf
import anotar_partitura as A

# --- referencias do sax alto, em altura escrita (MIDI)
GRAVE_EXTREMO = 61      # Sib3..Do#4: chaves de mindinho
AGUDO_PALMA = 84        # Do6 pra cima: chaves de palma
TOPO_NORMAL = 90        # Fa#6: acima disso e altissimo
QUEBRA = 73             # Do#5 -> Re5 e a virada da chave de oitava

ORDEM_CARACT = ["frac_altissimo", "frac_agudo", "frac_grave", "extensao",
                "dens", "frac_acid", "classes", "salto_med", "salto_max", "quebras"]

PESOS_ARQ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pesos_dificuldade.json")


def titulo_da_pagina(pg):
    """Titulo = o texto em NEGRITO mais alto da pagina (padrao do cadernin)."""
    cands = []
    for b in pg.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for sp in l.get("spans", []):
                t = sp.get("text", "").strip()
                if len(t) > 2 and "Bold" in sp.get("font", "") and sp["bbox"][1] < 120:
                    cands.append((sp["bbox"][1], -sp.get("size", 0), t))
    return sorted(cands)[0][2][:38] if cands else ""


def _caracteristicas_de(notas):
    if len(notas) < 12:
        return None
    notas = sorted(notas, key=lambda n: (n[0], n[1], n[3]))
    midis = [n[4] for n in notas]

    # densidade: notas por compasso (mediana, robusta a compasso de espera)
    por_compasso = {}
    for pag, sis, cmp_, _, _, _ in notas:
        por_compasso[(pag, sis, cmp_)] = por_compasso.get((pag, sis, cmp_), 0) + 1
    contagens = sorted(por_compasso.values())
    dens = contagens[len(contagens) // 2]

    # saltos e quebras de oitava: so entre notas vizinhas do MESMO sistema
    saltos, quebras = [], 0
    for a, b in zip(notas, notas[1:]):
        if (a[0], a[1]) != (b[0], b[1]):
            continue
        saltos.append(abs(b[4] - a[4]))
        if min(a[4], b[4]) <= QUEBRA < max(a[4], b[4]):
            quebras += 1
    saltos = saltos or [0]
    n = len(midis)

    return {
        "frac_altissimo": sum(1 for m in midis if m > TOPO_NORMAL) / n,
        "frac_agudo": sum(1 for m in midis if AGUDO_PALMA <= m <= TOPO_NORMAL) / n,
        "frac_grave": sum(1 for m in midis if m <= GRAVE_EXTREMO) / n,
        "extensao": max(midis) - min(midis),
        "dens": dens,
        "frac_acid": sum(1 for x in notas if x[5]) / n,
        "classes": len({m % 12 for m in midis}),
        "salto_med": sum(saltos) / len(saltos),
        "salto_max": max(saltos),
        "quebras": quebras / max(1, n - 1),
        "_n": n,
    }


def notas_do_pdf(caminho):
    """[(pagina, sistema, compasso, x, midi, alteracao)] + titulo por pagina."""
    doc = pymupdf.open(caminho)
    todas, titulos = [], {}
    for pg in doc:
        rot, _ = A.ler_notas(pg, "letras")
        titulos[pg.number] = titulo_da_pagina(pg)
        for r in rot:
            todas.append((pg.number, r["sistema"], r["compasso"], r["x"],
                          r["midi"], r["alt"]))
    doc.close()
    return todas, titulos


def caracteristicas(caminho):
    """Caracteristicas do PDF inteiro. None se nao houver nota legivel."""
    return _caracteristicas_de(notas_do_pdf(caminho)[0])


def caracteristicas_por_pagina(caminho):
    """Uma medicao por PAGINA — num caderno, cada pagina e uma musica."""
    todas, titulos = notas_do_pdf(caminho)
    por_pag = {}
    for n in todas:
        por_pag.setdefault(n[0], []).append(n)
    return [(pag, titulos.get(pag, ""), _caracteristicas_de(v))
            for pag, v in sorted(por_pag.items())]


def rotulo_de(nome):
    b = os.path.basename(nome).lower()
    if "beginner" in b:
        return 2.0
    if "easy" in b:
        return 1.5
    if "intermediate" in b:
        return 5.0
    if "advanced" in b:
        return 8.0
    return None


# ------------------------------------------------------------------ ajuste
def ajustar(X, y, iters=400):
    """Minimos quadrados com PESO NAO-NEGATIVO nas caracteristicas (intercepto livre).

    Sem essa restricao a colinearidade entre 'extensao' e 'salto_med' produzia peso
    NEGATIVO para salto: o modelo passava a dizer que salto grande facilita, o que e
    falso e quebraria fora do acervo. Descida por coordenada mantendo o residuo.
    """
    n, k = len(X), len(X[0])
    w = [0.0] * k
    w[0] = sum(y) / n
    r = [y[i] - w[0] for i in range(n)]
    norm = [sum(X[i][j] ** 2 for i in range(n)) or 1e-12 for j in range(k)]
    for _ in range(iters):
        for j in range(k):
            passo = sum(X[i][j] * r[i] for i in range(n)) / norm[j]
            novo = w[j] + passo
            if j:
                novo = max(0.0, novo)
            d = novo - w[j]
            if d:
                w[j] = novo
                for i in range(n):
                    r[i] -= d * X[i][j]
    return w


def calibrar(raiz):
    pdfs = []
    for dp, _, fns in os.walk(raiz):
        for fn in fns:
            if fn.lower().endswith(".pdf") and rotulo_de(fn) is not None \
                    and "alto" in fn.lower():
                pdfs.append(os.path.join(dp, fn))
    # o acervo tem pastas duplicadas: um arquivo por nome
    unicos = {}
    for p in pdfs:
        unicos.setdefault(os.path.basename(p).lower(), p)
    pdfs = sorted(unicos.values())
    print(f"{len(pdfs)} partituras de sax alto com rotulo", flush=True)

    dados = []
    for i, p in enumerate(pdfs):
        try:
            c = caracteristicas(p)
        except Exception:
            c = None
        if c:
            dados.append((p, c, rotulo_de(p)))
        if (i + 1) % 40 == 0:
            print(f"  {i+1}/{len(pdfs)}", flush=True)
    print(f"{len(dados)} com notas legiveis\n", flush=True)

    # padroniza as caracteristicas
    med, dp_ = {}, {}
    for k in ORDEM_CARACT:
        v = [d[1][k] for d in dados]
        med[k] = sum(v) / len(v)
        dp_[k] = math.sqrt(sum((x - med[k]) ** 2 for x in v) / len(v)) or 1.0

    X = [[1.0] + [(d[1][k] - med[k]) / dp_[k] for k in ORDEM_CARACT] for d in dados]
    y = [d[2] for d in dados]
    w = ajustar(X, y)

    # validacao cruzada: ajusta em 4/5 e preve o 1/5 que ficou de fora
    pred_cv = [None] * len(X)
    for f in range(5):
        tr = [i for i in range(len(X)) if i % 5 != f]
        te = [i for i in range(len(X)) if i % 5 == f]
        wf = ajustar([X[i] for i in tr], [y[i] for i in tr])
        for i in te:
            pred_cv[i] = sum(wi * xi for wi, xi in zip(wf, X[i]))

    pred = [sum(wi * xi for wi, xi in zip(w, x)) for x in X]
    ybar = sum(y) / len(y)
    r2 = 1 - sum((a - b) ** 2 for a, b in zip(y, pred)) / sum((a - ybar) ** 2 for a in y)

    print("peso por caracteristica (padronizada; + = mais dificil):")
    print(f"  {'(base)':16} {w[0]:+7.3f}")
    for k, wi in sorted(zip(ORDEM_CARACT, w[1:]), key=lambda kv: -abs(kv[1])):
        print(f"  {k:16} {wi:+7.3f}")
    ybar2 = sum(y) / len(y)
    r2cv = 1 - sum((a - b) ** 2 for a, b in zip(y, pred_cv)) / \
        sum((a - ybar2) ** 2 for a in y)
    print(f"\nR2 dentro da amostra = {r2:.3f}   |   R2 validado (5 folds) = {r2cv:.3f}")

    print("\nnota media prevista por rotulo:")
    for alvo, nome in [(1.5, "easy"), (2.0, "beginner"), (5.0, "intermediate"), (8.0, "advanced")]:
        g = [p for p, yy in zip(pred, y) if yy == alvo]
        if g:
            print(f"  {nome:13} n={len(g):4}  media={sum(g)/len(g):5.2f}  "
                  f"min={min(g):5.2f} max={max(g):5.2f}")

    # validacao forte: a MESMA musica em niveis diferentes tem de sair ordenada
    def tronco(p):
        b = os.path.basename(p).lower()
        b = re.sub(r'(beginner|easy|intermediate|advanced)', '', b)
        return re.sub(r'[^a-z]', '', b)

    grupos = {}
    for (p, _, yy), pr in zip(dados, pred_cv):
        grupos.setdefault(tronco(p), []).append((yy, pr, os.path.basename(p)))
    pares_ok = pares = 0
    for g in grupos.values():
        for i in range(len(g)):
            for j in range(len(g)):
                if g[i][0] < g[j][0]:
                    pares += 1
                    pares_ok += g[i][1] < g[j][1]
    print(f"\nordenacao dentro da MESMA musica (com previsao VALIDADA): "
          f"{pares_ok}/{pares} pares na ordem certa"
          f" = {100*pares_ok/pares if pares else 0:.1f}%")

    json.dump({"pesos": w, "media": med, "desvio": dp_, "ordem": ORDEM_CARACT},
              open(PESOS_ARQ, "w"), indent=1)
    print(f"\n-> {PESOS_ARQ}")


# ------------------------------------------------------------------- nota
def nota(caminho, cal):
    c = caracteristicas(caminho)
    if not c:
        return None, None
    x = [1.0] + [(c[k] - cal["media"][k]) / cal["desvio"][k] for k in cal["ordem"]]
    v = sum(wi * xi for wi, xi in zip(cal["pesos"], x))
    return max(0.0, min(10.0, v)), c


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    if sys.argv[1] == "calibrar":
        calibrar(sys.argv[2])
        return 0
    if not os.path.exists(PESOS_ARQ):
        print("Rode primeiro:  uv run dificuldade.py calibrar <raiz_do_acervo>", file=sys.stderr)
        return 1
    cal = json.load(open(PESOS_ARQ))
    if sys.argv[1] == "paginas":
        for p in sys.argv[2:]:
            linhas = []
            for pag, tit, c in caracteristicas_por_pagina(p):
                if not c:
                    continue
                x = [1.0] + [(c[k] - cal["media"][k]) / cal["desvio"][k] for k in cal["ordem"]]
                v = max(0.0, min(10.0, sum(wi * xi for wi, xi in zip(cal["pesos"], x))))
                linhas.append((v, pag + 1, tit, c))
            print(f"\n{os.path.basename(p)} — {len(linhas)} paginas com musica, "
                  f"da mais dificil para a mais facil:")
            print(f"{'nota':>5} {'pag':>4}  {'ext':>4} {'n/comp':>6} {'%alt':>5}  titulo")
            for v, pag, tit, c in sorted(linhas, reverse=True):
                print(f"{v:5.1f} {pag:4d}  {c['extensao']:4d} {c['dens']:6d} "
                      f"{100*c['frac_acid']:4.0f}%  {tit}")
        return 0
    alvos = []
    for a in sys.argv[2:]:
        alvos.extend(sorted(glob.glob(a)) if any(ch in a for ch in "*?[") else [a])
    print(f"{'nota':>5}  {'reg.escrito':>13} {'n/comp':>6} {'%alt':>5} {'salto':>5}  arquivo")
    for p in alvos:
        try:
            v, c = nota(p, cal)
        except Exception as e:
            print(f"{'-':>5}  erro: {type(e).__name__}  {os.path.basename(p)[:50]}")
            continue
        if v is None:
            print(f"{'-':>5}  sem nota legivel        {os.path.basename(p)[:50]}")
            continue
        print(f"{v:5.1f}  {c['extensao']:5d} semit  {c['dens']:6d} "
              f"{100*c['frac_acid']:4.0f}% {c['salto_med']:5.1f}  {os.path.basename(p)[:60]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
