#!/usr/bin/env python3
"""
anotar_partitura — escreve o nome de cada nota embaixo da pauta, no PDF original.

Le os glifos SMuFL do PDF (export do MuseScore/Dorico: fontes Leland, Bravura,
Petaluma...) e as linhas da pauta desenhadas em vetor. Com clave + armadura +
acidentes, calcula a altura de cada cabeca de nota e estampa o nome. O PDF de
saida e o original com uma camada de texto a mais: nada e re-desenhado.

Uso:  uv run anotar_partitura.py "partitura.pdf"

Baseado na tecnica de extracao vetorial de vitorfornaro/awesome-music-sheets
(tools/vector_extract.py).
"""
import argparse
import collections
import os
import re
import sys

try:                      # PyMuPDF >= 1.24 usa o nome pymupdf; fitz e o alias antigo
    import pymupdf as fitz
except ImportError:
    import fitz

# --------------------------------------------------------- perfis de fonte
# Dois mundos de codificacao:
#   smufl  -> MuseScore/Dorico (Leland, Bravura, Petaluma...): codepoints padrao SMuFL
#   sonata -> Finale/Sibelius (Maestro, Opus...): layout legado Adobe Sonata
# Cada glifo e traduzido para um TIPO no momento da coleta, e o resto do codigo
# nao sabe de qual fonte veio.
#
# indice diatonico da LINHA SUPERIOR da pauta (C0 == 0):
#   clave de sol -> linha de cima = F5 = 5*7+3 = 38
#   clave de fa  -> linha de cima = A3 = 3*7+5 = 26
#   clave de do  -> linha de cima = G4 = 4*7+4 = 32
#
# "cabecas" mapeia o codepoint para a DURACAO BASE da figura, em tempos de seminima
# (semibreve 4, minima 2, seminima 1). Bandeirola/beam divide isso por 2 a cada nivel.
PERFIS = {
    "smufl": {
        "cabecas": {0xE0A0: 8, 0xE0A1: 8, 0xE0A2: 4, 0xE0A3: 2, 0xE0A4: 1},
        "acidentes": {0xE260: 'b', 0xE261: 'n', 0xE262: '#', 0xE263: '##', 0xE264: 'bb'},
        "claves": {0xE050: 38, 0xE051: 38, 0xE052: 38, 0xE053: 38, 0xE054: 38,
                   0xE062: 26, 0xE063: 26, 0xE064: 26, 0xE065: 26, 0xE05C: 32},
        # bandeirola -> quantos niveis (1 = colcheia, 2 = semicolcheia...). Par = cima/baixo.
        "bandeiras": {0xE240: 1, 0xE241: 1, 0xE242: 2, 0xE243: 2, 0xE244: 3, 0xE245: 3,
                      0xE246: 4, 0xE247: 4, 0xE248: 5, 0xE249: 5, 0xE24A: 6, 0xE24B: 6},
        "pontos": {0xE1E7},
        "pausas": {0xE4E2: 8, 0xE4E3: 4, 0xE4E4: 2, 0xE4E5: 1, 0xE4E6: 0.5,
                   0xE4E7: 0.25, 0xE4E8: 0.125, 0xE4E9: 0.0625, 0xE4EA: 0.03125},
    },
    "sonata": {
        # confirmados nos PDFs de teste: 'oe'=cabeca preta, ponto=branca, w=semibreve,
        # &=clave de sol (aparece 1x por pauta), #/b/n=acidentes.
        "cabecas": {0x153: 1, 0x2D9: 2, 0x77: 4},
        "acidentes": {0x62: 'b', 0x6E: 'n', 0x23: '#'},
        "claves": {0x26: 38, 0x3F: 26, 0x42: 32},   # sol confirmado; fa/do pelo layout Sonata
        # medidos no The-chicken/Song_of_somg: minusculo = haste pra cima, MAIUSCULO = pra
        # baixo. So entram os niveis que eu vi de fato; fusa nao foi medida, fica de fora.
        "bandeiras": {0x6A: 1, 0x4A: 1, 0x72: 2, 0x52: 2},
        # 0x2E no Maestro/Finale; 0x2122 e o ponto do Sibelius, que mora na fonte
        # OpusSpecialStd — sem ele toda pausa pontuada do The-chicken saia curta.
        "pontos": {0x2E, 0x2122},
        "pausas": {0x2211: 4, 0xD3: 2, 0x152: 1, 0x2030: 0.5, 0x2248: 0.25},
    },
}

# prefixo de nome de fonte -> perfil. Fontes de CIFRA ("OpusChordsSans") sao
# descartadas: o 'b' de "Bb" viraria bemol.
FONTES_MUSICA = [
    ("Leland", "smufl"), ("Bravura", "smufl"), ("Petaluma", "smufl"),
    ("Emmentaler", "smufl"), ("MuseJazz", "smufl"), ("Sebastian", "smufl"),
    ("November", "smufl"), ("Gonville", "smufl"), ("Finale Maestro", "smufl"),
    ("Maestro", "sonata"), ("Opus", "sonata"), ("Sonata", "sonata"),
    ("Petrucci", "sonata"), ("Engraver", "sonata"), ("Inkpen", "sonata"),
]
FONTES_IGNORADAS = ("Chord", "Figured", "Percussion")


def perfil_da_fonte(nome):
    if any(k in nome for k in FONTES_IGNORADAS):
        return None
    for prefixo, perfil in FONTES_MUSICA:
        if nome.startswith(prefixo):
            return perfil
    return None


DIATONICAS = ['C', 'D', 'E', 'F', 'G', 'A', 'B']
SOLFEJO = {'C': 'Do', 'D': 'Re', 'E': 'Mi', 'F': 'Fa', 'G': 'Sol', 'A': 'La', 'B': 'Si'}
ORDEM_SUSTENIDOS = ['F', 'C', 'G', 'D', 'A', 'E', 'B']
ORDEM_BEMOIS = ['B', 'E', 'A', 'D', 'G', 'C', 'F']

# nomes de nota ja escritos na partitura (para --limpar)
# Sem digito no fim: "G7"/"C7" e cifra, nao nome de nota.
RE_NOME_NOTA = re.compile(r'^(Do|Re|Mi|Fa|Sol|La|Si|[A-G])(#|##|b|bb|)$')
_SOLFEJO_SET = set(SOLFEJO.values())


def familia(txt):
    """'dore' para Do/Re/Mi..., 'letras' para C/D/E... — usado por --limpar."""
    return 'dore' if txt.rstrip('#b') in _SOLFEJO_SET else 'letras'



# ------------------------------------------------------------------- coleta
def escala(pg):
    """Fator da pagina em relacao ao A4 de referencia (595x842), pela altura."""
    return pg.rect.height / 842.0


def coletar(pg, com_ritmo=False):
    """Glifos musicais, spans de texto comum, linhas horizontais e verticais.

    Com `com_ritmo`, tambem devolve os BEAMS (7o item) e inclui em `glifos` as
    bandeirolas, os pontos de aumento e as pausas. Fica atras de uma flag porque
    varios scripts desempacotam o resultado em 6 nomes.
    """
    glifos, textos = [], []
    for b in pg.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            for s in l.get("spans", []):
                base = s.get("font", "").split('+')[-1]
                perfil = perfil_da_fonte(base)
                if perfil:
                    P = PERFIS[perfil]
                    # A cabeca de nota e desenhada SOBRE a linha de base do glifo, mas o
                    # bbox que o PyMuPDF devolve tem a altura da linha de texto inteira
                    # (ascender..descender). Reconstroi a base a partir das metricas do
                    # span — exato e por caractere, sem constante chutada por familia de
                    # fonte (as metricas variam de arquivo para arquivo).
                    ajuste = 0.5 * s.get("size", 0) * (s.get("ascender", 0)
                                                       + s.get("descender", 0))
                    for ch in s.get("chars", []):
                        cp, bb = ord(ch["c"]), ch["bbox"]
                        if cp in P["cabecas"]:
                            tipo, extra = "cabeca", P["cabecas"][cp]
                        elif cp in P["acidentes"]:
                            tipo, extra = "acc", P["acidentes"][cp]
                        elif cp in P["claves"]:
                            tipo, extra = "clave", P["claves"][cp]
                        elif com_ritmo and cp in P["bandeiras"]:
                            tipo, extra = "bandeira", P["bandeiras"][cp]
                        elif com_ritmo and cp in P["pontos"]:
                            tipo, extra = "ponto", None
                        elif com_ritmo and cp in P["pausas"]:
                            tipo, extra = "pausa", P["pausas"][cp]
                        else:
                            continue
                        glifos.append({"tipo": tipo, "extra": extra,
                                       "x": (bb[0] + bb[2]) / 2,
                                       "y": (bb[1] + bb[3]) / 2 + ajuste,
                                       "sz": s.get("size", 0),
                                       "x0": bb[0], "x1": bb[2], "y0": bb[1], "y1": bb[3]})
                else:
                    # Quebra o span em PALAVRAS: o PyMuPDF funde rotulos vizinhos num
                    # unico span ("Fa La"), e ai o nome de nota nao seria reconhecido.
                    corpo = s.get("size", s["bbox"][3] - s["bbox"][1])
                    base_y = s.get("origin", (0, s["bbox"][3]))[1]
                    palavra = []
                    for ch in list(s.get("chars", [])) + [None]:
                        # Quebra por espaco, por folga em x, e tambem antes de MAIUSCULA
                        # quando o acumulado ja e um nome de nota: o plugin cola os nomes
                        # sem espaco ("FaLa"). Nao parte "Sib" nem "Do#" (minusculo/simbolo).
                        quebra = (ch is None or not ch["c"].strip()
                                  or (palavra and ch["bbox"][0] - palavra[-1]["bbox"][2] > 0.22 * corpo)
                                  or (palavra and ch["c"].isupper()
                                      and RE_NOME_NOTA.match(''.join(c["c"] for c in palavra))))
                        if quebra and palavra:
                            textos.append({
                                "txt": ''.join(c["c"] for c in palavra),
                                "bbox": (palavra[0]["bbox"][0], s["bbox"][1],
                                         palavra[-1]["bbox"][2], s["bbox"][3]),
                                "fonte": base, "base_y": base_y, "corpo": corpo,
                                "x0": palavra[0]["bbox"][0], "x1": palavra[-1]["bbox"][2]})
                            palavra = []
                        if ch is not None and ch["c"].strip():
                            palavra.append(ch)

    # Os limiares abaixo sao os valores validados em A4 (595x842) multiplicados pela
    # ESCALA da pagina: o mesmo A4 aparece gravado em escalas bem diferentes (ja vi
    # 595x842 e 2976x4209 na mesma pasta). Em A4 o comportamento e identico ao de antes.
    k = escala(pg)
    esp_max = 1.0 * k             # espessura maxima de um traco "fino"
    comp_min = 20.0 * k           # comprimento minimo de uma horizontal
    alt_min = 4.0 * k             # altura minima de uma vertical

    horiz, vert, formas, caminhos, beams = [], [], [], [], []
    for p in pg.get_drawings():
        r = p["rect"]
        if r.height < 250 * k and r.width < 250 * k:   # hastes, beams, ligaduras, colchetes
            formas.append({"x": (r.x0 + r.x1) / 2, "y": (r.y0 + r.y1) / 2,
                           "x0": r.x0, "x1": r.x1, "y0": r.y0, "y1": r.y1})
        if p.get("fill") is not None and r.width > 0 and r.height > 0:
            caminhos.append({"x0": r.x0, "x1": r.x1, "y0": r.y0, "y1": r.y1,
                             "w": r.width, "h": r.height,
                             "curvas": sum(1 for it in p["items"] if it[0] == "c")})
        if com_ritmo:
            b = _beam(p)
            if b:
                beams.append(b)
        for it in p["items"]:
            if it[0] == "l":
                p1, p2 = it[1], it[2]
            elif it[0] == "re":                      # linha fina desenhada como retangulo
                r = it[1]
                if r.height < esp_max and r.width > comp_min:
                    horiz.append((round((r.y0 + r.y1) / 2, 2), r.x0, r.x1))
                elif r.width < 1.2 * esp_max and r.height > alt_min:
                    vert.append({"x": (r.x0 + r.x1) / 2, "y0": r.y0, "y1": r.y1, "h": r.height})
                continue
            else:
                continue
            if abs(p1.y - p2.y) < esp_max and abs(p2.x - p1.x) > comp_min:
                horiz.append((round(p1.y, 2), min(p1.x, p2.x), max(p1.x, p2.x)))
            elif abs(p1.x - p2.x) < 1.2 * k and abs(p2.y - p1.y) > alt_min:
                vert.append({"x": p1.x, "y0": min(p1.y, p2.y), "y1": max(p1.y, p2.y),
                             "h": abs(p2.y - p1.y)})
    if com_ritmo:
        return glifos, textos, horiz, vert, formas, caminhos, beams
    return glifos, textos, horiz, vert, formas, caminhos


def _beam(p):
    """Barra de ligacao (beam) -> paralelogramo preenchido, fino e inclinado.

    Nao da para usar a altura do bbox: um beam longo e inclinado tem bbox alto. A
    espessura tem de ser medida NA BORDA — os dois y's que existem em x0 e em x1.
    Devolve as duas retas de topo/base para saber onde o beam passa em cada x.
    """
    if p.get("fill") is None:
        return None
    pts = []
    for it in p["items"]:
        if it[0] == "l":
            pts += [(it[1].x, it[1].y), (it[2].x, it[2].y)]
        elif it[0] == "re":
            r = it[1]
            pts += [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)]
        elif it[0] == "qu":
            pts += [(q.x, q.y) for q in it[1]]
        else:
            return None                      # tem curva: e ligadura, cabeca ou pausa
    if len(pts) < 4:
        return None
    xs = [q[0] for q in pts]
    x0, x1 = min(xs), max(xs)
    larg = x1 - x0
    if larg <= 0:
        return None
    tol = max(0.02 * larg, 0.05)
    esq = [q[1] for q in pts if q[0] <= x0 + tol]
    dir_ = [q[1] for q in pts if q[0] >= x1 - tol]
    if len(esq) < 2 or len(dir_) < 2:
        return None                          # triangulo, cunha: nao e beam
    return {"x0": x0, "x1": x1, "larg": larg,
            "topo0": min(esq), "topo1": min(dir_),
            "base0": max(esq), "base1": max(dir_),
            "esp0": max(esq) - min(esq), "esp1": max(dir_) - min(dir_)}


def _cobertura(segs):
    """Comprimento total coberto por segmentos, sem contar sobreposicao duas vezes."""
    total, fim = 0.0, None
    for a, b in sorted(segs):
        if fim is None or a > fim:
            total += b - a
            fim = b
        elif b > fim:
            total += b - fim
            fim = b
    return total


def pautas(horiz, largura_pagina, altura_pagina):
    """Agrupa as linhas horizontais em pautas: 5 linhas longas e igualmente espacadas.

    Filtra por comprimento (linha de pauta atravessa o sistema; beam/crescendo nao) e
    exige espacamento uniforme, senao um beam colado na pauta entra no lugar de uma linha.
    Os limiares sao fracoes da pagina: o mesmo A4 aparece em escalas bem diferentes.
    """
    niveis = {}
    for y, x0, x1 in horiz:
        niveis.setdefault(round(y, 1), []).append((x0, x1))
    if not niveis:
        return []

    # Junta niveis quase coincidentes (mesma linha desenhada em duas passadas). Duas
    # regras importam aqui: a cobertura do grupo e a UNIAO dos segmentos (somando, um
    # punhado de tracos curtos empilhados virava "linha longa" fantasma), e o y do
    # grupo e o do nivel de MAIOR cobertura (a linha real), nao o primeiro.
    k = altura_pagina / 842.0
    junta_max = 1.2 * k
    grupos = []
    for y, segs in sorted(niveis.items()):
        c = _cobertura(segs)
        if grupos and y - grupos[-1]["ult"] < junta_max:
            g = grupos[-1]
            g["segs"].extend(segs)
            g["ult"] = y
            if c > g["dom"]:
                g["dom"], g["y"] = c, y
        else:
            grupos.append({"y": y, "ult": y, "segs": list(segs), "dom": c})
    juntos = [(g["y"], _cobertura(g["segs"])) for g in grupos]

    corte = 0.15 * largura_pagina
    longas = sorted((y, c) for y, c in juntos if c >= corte and c < largura_pagina * 0.99)
    if len(longas) < 5:
        return []
    ys = [y for y, _ in longas]

    # Passo tipico entre linhas de pauta = moda dos vaos plausiveis, refinada numa
    # janela ESTREITA: vao de colchete (~3/4 do passo) contamina a media e desalinha
    # a progressao o suficiente para escolher a linha errada la na 5a.
    gaps = [b - a for a, b in zip(ys, ys[1:]) if 2.0 * k <= b - a <= 14.0 * k]
    if not gaps:
        return []
    faixa = 0.25 * k
    modo = collections.Counter(round(g / faixa) for g in gaps).most_common(1)[0][0] * faixa
    perto = [g for g in gaps if abs(g - modo) <= max(0.5 * k, 0.06 * modo)] or [modo]
    d = sum(perto) / len(perto)
    tol = 0.28 * d

    # Procura 5 linhas em PROGRESSAO de passo d — por periodicidade, nao por
    # adjacencia, o que tolera beam/colchete intercalado. Entre os candidatos de cada
    # degrau, prefere o MAIS LONGO: linha de pauta cruza o sistema, colchete nao.
    # As sementes sao testadas da linha MAIS LONGA para a mais curta, para a pauta
    # verdadeira se formar antes que uma fantasma consuma as linhas dela.
    ordem = sorted(range(len(longas)), key=lambda i: (-longas[i][1], ys[i]))
    usados, achadas = set(), []
    for i in ordem:
        if i in usados:
            continue
        y = ys[i]
        linhas, idx = [y], [i]
        for m in range(1, 5):
            alvo = y + m * d
            melhor = None
            for j in range(len(longas)):
                if j in usados or j == i or abs(ys[j] - alvo) > tol:
                    continue
                if melhor is None or (longas[j][1], -abs(ys[j] - alvo)) > \
                        (longas[melhor][1], -abs(ys[melhor] - alvo)):
                    melhor = j
            if melhor is None:
                break
            linhas.append(ys[melhor])
            idx.append(melhor)
        if len(linhas) < 5:
            continue
        # As 5 linhas de uma pauta tem praticamente o mesmo comprimento. Se uma delas
        # for muito mais curta, o grupo pegou uma linha que nao e de pauta.
        cobs = [longas[j][1] for j in idx]
        if min(cobs) < 0.55 * max(cobs):
            continue
        achadas.append(sorted(linhas))
        usados.update(idx)
    return sorted(achadas, key=lambda g: g[0])


# ------------------------------------------- glifos por CONTORNO (sem fonte)
# Alguns PDFs convertem os simbolos musicais em curvas, e ai nao ha caractere para
# ler. Mas a geometria e inconfundivel quando medida em ESPACOS de pauta:
#   cabeca de nota  ~1.3 x 1.05   preenchida, com curva
#   sustenido       ~1.0 x 2.7    centro na altura da nota
#   bequadro        ~0.7 x 2.6    centro na altura da nota, mais estreito
#   bemol           ~0.8 x 2.5    bojo NA nota, haste acima -> nota 1/2 espaco abaixo
#   clave de sol    ~2.6 x 7.1
# Medido no acervo do Manuel: 435 sustenidos, 234 bequadros, 114 bemois.
CABECA_W = (1.05, 1.60)
CABECA_H = (0.80, 1.35)
ACC_W = (0.50, 1.20)
ACC_H = (2.20, 3.10)
CURVAS_VAZIA = 14        # cabeca vazada tem contorno de fora E de dentro: o dobro de curvas
PONTO_D = (0.22, 0.60)   # ponto de aumento: redondinho, menos de meio espaco


def glifos_de_contorno(caminhos, sistemas):
    """Reconstroi cabecas, acidentes e claves a partir da geometria das curvas."""
    glifos = []
    for linhas in sistemas:
        esp = (linhas[-1] - linhas[0]) / 4.0
        topo, base = linhas[0], linhas[-1]
        na_faixa = lambda c: topo - 5 * esp < (c["y0"] + c["y1"]) / 2 < base + 5 * esp
        aqui = [c for c in caminhos if na_faixa(c)]

        cabecas = [c for c in aqui
                   if CABECA_W[0] <= c["w"] / esp <= CABECA_W[1]
                   and CABECA_H[0] <= c["h"] / esp <= CABECA_H[1] and c["curvas"]]
        if not cabecas:
            continue
        larg_nota = sorted(c["w"] for c in cabecas)[len(cabecas) // 2]
        for c in cabecas:
            # sem codepoint, o que separa minima de seminima e o buraco no meio:
            # a cabeca vazada tem duas curvas fechadas, a preta so uma.
            vazia = c["curvas"] >= CURVAS_VAZIA
            glifos.append({"tipo": "cabeca", "extra": 2 if vazia else 1, "vazia": vazia,
                           "sz": c["w"],
                           "x": (c["x0"] + c["x1"]) / 2, "y": (c["y0"] + c["y1"]) / 2,
                           "x0": c["x0"], "x1": c["x1"], "y0": c["y0"], "y1": c["y1"]})

        for c in aqui:
            if (PONTO_D[0] <= c["w"] / esp <= PONTO_D[1]
                    and PONTO_D[0] <= c["h"] / esp <= PONTO_D[1]
                    and abs(c["w"] - c["h"]) < 0.18 * esp and c["curvas"]):
                glifos.append({"tipo": "ponto", "extra": None, "sz": c["w"],
                               "x": (c["x0"] + c["x1"]) / 2, "y": (c["y0"] + c["y1"]) / 2,
                               "x0": c["x0"], "x1": c["x1"], "y0": c["y0"], "y1": c["y1"]})

        # clave: a forma bem alta a esquerda do sistema
        claves = [c for c in aqui if c["h"] / esp > 5.5 and 1.5 < c["w"] / esp < 4.0]
        for c in claves:
            glifos.append({"tipo": "clave", "extra": 38,      # so clave de sol no acervo
                           "x": (c["x0"] + c["x1"]) / 2, "y": (c["y0"] + c["y1"]) / 2,
                           "x0": c["x0"], "x1": c["x1"], "y0": c["y0"], "y1": c["y1"]})

        x_primeira = min(c["x0"] for c in cabecas)
        for c in aqui:
            if not (ACC_W[0] <= c["w"] / esp <= ACC_W[1]
                    and ACC_H[0] <= c["h"] / esp <= ACC_H[1]):
                continue
            cy = (c["y0"] + c["y1"]) / 2
            viz = [h for h in cabecas
                   if -0.2 * esp <= h["x0"] - c["x1"] < 1.3 * esp
                   and abs((h["y0"] + h["y1"]) / 2 - cy) < 0.8 * esp]
            if viz:
                h = min(viz, key=lambda h: h["x0"] - c["x1"])
                dy = (((h["y0"] + h["y1"]) / 2) - cy) / esp
            elif c["x1"] < x_primeira:
                dy = None          # candidato a armadura: nao tem nota colada
            else:
                continue           # pausa, bandeirola: nao e acidente
            # bemol tem o bojo NA nota, entao a nota fica meio espaco abaixo do centro
            if dy is not None and dy >= 0.30:
                simbolo = 'b'
            elif c["w"] >= 0.64 * larg_nota:
                simbolo = '#'
            else:
                simbolo = 'n'
            # na armadura o bemol nao tem nota vizinha: usa a largura para separar
            if dy is None and 'b' != simbolo and c["w"] < 0.72 * larg_nota:
                simbolo = 'n'
            glifos.append({"tipo": "acc", "extra": simbolo,
                           "x": (c["x0"] + c["x1"]) / 2,
                           "y": cy + (0.5 * esp if simbolo == 'b' else 0.0),
                           "x0": c["x0"], "x1": c["x1"], "y0": c["y0"], "y1": c["y1"]})
    return glifos


# ------------------------------------------------------------------- alturas
def indice_diatonico(cy, linhas, topo_ref):
    """Posicao vertical -> indice diatonico (C0 == 0)."""
    span = linhas[-1] - linhas[0]
    meio_espaco = span / 8.0
    passos = round((linhas[0] - cy) / meio_espaco)
    return topo_ref + passos


def armadura(glifos, linhas, x_clave, topo_ref, cabecas):
    """Le a armadura de clave -> alteracoes por letra + os x que nao sao acidente solto.

    A armadura e o grupo contiguo logo depois da clave, e para no primeiro acidente que
    tenha uma CABECA DE NOTA colada a direita, na mesma altura — esse e da nota.

    So medir "esta antes da primeira nota" nao serve: o acidente da primeira nota fica
    a 1-2pt dela, dentro de qualquer margem razoavel, e ia para a armadura — a nota
    perdia o sustenido e o tom saia errado para a linha toda.

    Nao da para checar as LETRAS canonicas (F C G D...) aqui: a posicao vertical do
    glifo de bemol nao e a da nota (o bojo fica abaixo do centro da caixa), e a checagem
    passava a rejeitar armadura de bemol.
    """
    span = linhas[-1] - linhas[0]
    accs = sorted([g for g in glifos if g["tipo"] == "acc" and g["extra"] in ('#', 'b')
                   and g["x0"] >= x_clave], key=lambda g: g["x0"])

    def colada(g):
        """Nota logo a direita e na mesma altura: o acidente e dela, nao da armadura.

        O limiar de 0.25 span vem de medicao: acidente de NOTA fica a ~0.09 span da
        cabeca; acidente de ARMADURA, a 0.49 span ou mais (mesmo em sistema de
        continuacao, que nao tem formula de compasso no meio).
        """
        return any(-0.1 * span <= h["x0"] - g["x1"] < 0.25 * span
                   and abs(h["y"] - g["y"]) < 0.35 * span for h in cabecas)

    entre, borda = [], x_clave
    for g in accs:
        if g["x0"] - borda > 2.0 * span or colada(g) or len(entre) >= 7:
            break
        entre.append(g)
        borda = g["x1"]

    s = sum(1 for g in entre if g["extra"] == '#')
    b = sum(1 for g in entre if g["extra"] == 'b')
    if s and not b:
        return {n: '#' for n in ORDEM_SUSTENIDOS[:s]}, {g["x"] for g in entre}
    if b and not s:
        return {n: 'b' for n in ORDEM_BEMOIS[:b]}, {g["x"] for g in entre}
    return {}, set()


SEMITONS = [0, 2, 4, 5, 7, 9, 11]          # C D E F G A B dentro da oitava


def midi_de(idx, alt):
    """Indice diatonico (C0 == 0) + alteracao -> numero MIDI (C0 == 12)."""
    desvio = {'': 0, '#': 1, 'b': -1, '##': 2, 'bb': -2}.get(alt, 0)
    return 12 + 12 * (idx // 7) + SEMITONS[idx % 7] + desvio


def nome(idx, alt, sistema):
    letra = DIATONICAS[idx % 7]
    base = SOLFEJO[letra] if sistema == 'dore' else letra
    return base + alt


# -------------------------------------------------------------------- duracao
BEAM_ESP = (0.22, 1.00)      # espessura de um beam, em espacos de pauta
BEAM_LARG = 0.35             # largura minima (o "gancho" de nota solta e curtinho)


def _haste_de(h, vert, esp):
    """A haste da cabeca: vertical colada na borda esquerda (pra baixo) ou direita (pra cima).

    O que define a haste e ela ENCOSTAR na cabeca: uma das pontas cai em cima do
    centro da cabeca. Sem essa exigencia, a haste da apojatura vizinha entra como
    candidata, ganha por ser mais comprida, e a nota perde os beams dela.
    """
    melhor = None
    for v in vert:
        if v["h"] < 1.2 * esp:
            continue
        sobe = (abs(v["x"] - h["x1"]) < 0.45 * esp
                and abs(v["y1"] - h["y"]) < 0.6 * esp and v["y0"] < h["y"] - 0.9 * esp)
        desce = (abs(v["x"] - h["x0"]) < 0.45 * esp
                 and abs(v["y0"] - h["y"]) < 0.6 * esp and v["y1"] > h["y"] + 0.9 * esp)
        if not (sobe or desce):
            continue
        if melhor is None or v["h"] > melhor["h"]:
            melhor = v
    return melhor


def _niveis(hs, beams, bandeiras, esp):
    """Quantos beams/bandeirolas cortam a haste -> 1 = colcheia, 2 = semicolcheia..."""
    if hs is None:
        return 0
    sx = hs["x"]
    n = 0
    for b in beams:
        if b["larg"] < BEAM_LARG * esp or not (b["x0"] - 0.3 * esp <= sx <= b["x1"] + 0.3 * esp):
            continue
        if not (BEAM_ESP[0] * esp <= b["esp0"] <= BEAM_ESP[1] * esp
                and BEAM_ESP[0] * esp <= b["esp1"] <= BEAM_ESP[1] * esp):
            continue
        t = min(1.0, max(0.0, (sx - b["x0"]) / b["larg"]))
        yc = (b["topo0"] + (b["topo1"] - b["topo0"]) * t
              + b["base0"] + (b["base1"] - b["base0"]) * t) / 2
        if hs["y0"] - 0.7 * esp <= yc <= hs["y1"] + 0.7 * esp:
            n += 1
    if n:
        return n
    for g in bandeiras:
        if (-0.4 * esp < g["x"] - sx < 2.2 * esp
                and hs["y0"] - 0.8 * esp <= g["y"] <= hs["y1"] + 0.8 * esp):
            n = max(n, g["extra"])
    return n


GRACA = 0.85            # cabeca menor que isso x a mediana e apojatura (nao ocupa tempo)
LIG_ALT = 2.2           # altura maxima do arco de ligadura, em espacos de pauta
LIG_LARG = (0.55, 18.0) # largura minima e maxima do arco


def ligaduras_de(caminhos, notas, esp, pausas=()):
    """{indice da nota que so continua o som: indice da nota que comeca o som}.

    Ligadura de VALOR e um arco entre duas cabecas VIZINHAS e de MESMA altura. Com
    alturas diferentes o arco e fraseado (slur) e nao muda nome nenhum. Exigir que
    sejam vizinhas e o que separa a ligadura de um fraseado longo que por acaso
    comeca e termina na mesma nota — sem isso, "G ... G" com meio compasso no meio
    viraria uma nota so.
    """
    if len(notas) < 2:
        return {}
    arcos = [c for c in caminhos
             if 2 <= c["curvas"] <= 4 and c["h"] <= LIG_ALT * esp
             and LIG_LARG[0] * esp <= c["w"] <= LIG_LARG[1] * esp]

    def ponta(x, c):
        cand = [(k, n[0]) for k, n in enumerate(notas)
                if abs(n[0]["x"] - x) < 1.5 * esp
                and min(abs(n[0]["y"] - c["y0"]), abs(n[0]["y"] - c["y1"])) < 1.7 * esp]
        return min(cand, key=lambda kn: abs(kn[1]["x"] - x))[0] if cand else None

    out = {}
    for c in arcos:
        i, j = ponta(c["x0"], c), ponta(c["x1"], c)
        if i is None or j is None or j != i + 1:
            continue
        if notas[i][2] != notas[j][2] or notas[i][3] != notas[j][3]:
            continue                       # alturas diferentes -> e fraseado
        xi, xj = notas[i][0]["x"], notas[j][0]["x"]
        if any(xi < p["x"] < xj for p in pausas):
            continue                       # tem pausa no meio: o som nao continua
        out[j] = i
    return out


def _e_ritornello(p, pontos, barras, esp):
    """Os dois pontinhos da barra de repeticao, que na fonte Sonata sao o mesmo '.'.

    Assinatura: par no MESMO x, um espaco de distancia, encostado numa barra de
    compasso. Sem isso eles viravam ponto de aumento da nota anterior.
    """
    if not any(abs(b - p["x"]) < 2.2 * esp for b in barras):
        return False
    return any(q is not p and abs(q["x"] - p["x"]) < 0.25 * esp
               and 0.6 * esp < abs(q["y"] - p["y"]) < 1.4 * esp for q in pontos)


def _pontos_de(alvos, pontos, esp, folga_y):
    """Ponto de aumento -> quantos cada alvo (cabeca ou pausa) recebeu.

    A amarracao e 1:1 e no sentido PONTO -> alvo, igual a dos acidentes. Contar do
    outro lado ("tem ponto a direita?") faz o mesmo ponto valer para a nota dele e
    para a vizinha de tras, e o compasso sai com meio tempo a mais.
    """
    n = collections.Counter()
    for p in sorted(pontos, key=lambda p: p["x"]):
        cand = [a for a in alvos if 0.15 * esp < p["x"] - a["x1"] < 2.6 * esp
                and abs(p["y"] - a["y"]) < folga_y * esp]
        if cand:
            n[id(max(cand, key=lambda a: a["x1"]))] += 1
    return n


def duracao_das(cabecas, pausas, vert, beams, bandeiras, pontos, barras, esp):
    """(duracao das cabecas, duracao das pausas), em tempos de seminima.

    cabecas: id -> (duracao, e_apojatura).  pausas: id -> duracao.
    """
    # apojatura vem em corpo reduzido: comparar TAMANHO DE FONTE, nao largura da
    # cabeca — semibreve e mais larga que minima, e a minima virava apojatura.
    tam = sorted(h.get("sz") or 0 for h in cabecas)
    med = tam[len(tam) // 2] if tam else 0
    pontos = [p for p in pontos if not _e_ritornello(p, pontos, barras, esp)]
    n_pontos = _pontos_de(list(cabecas) + list(pausas), pontos, esp, 1.4)
    out = {}
    for h in cabecas:
        graca = bool(med) and (h.get("sz") or 0) < GRACA * med
        base = h.get("extra") or 1
        if base <= 1:
            base = base / (2 ** _niveis(_haste_de(h, vert, esp), beams, bandeiras, esp))
        elif h.get("vazia") and _haste_de(h, vert, esp) is None:
            base = 4          # cabeca vazada SEM haste so pode ser semibreve
        d = n_pontos.get(id(h), 0)
        out[id(h)] = (base * (2 - 0.5 ** d) if d else base, graca)
    out_p = {id(p): p["extra"] * (2 - 0.5 ** n_pontos[id(p)]) if n_pontos.get(id(p))
             else p["extra"] for p in pausas}
    return out, out_p


# --------------------------------------------------------------------- leitura
def ler_notas(pg, sistema, com_pausas=False):
    """Retorna (rotulos, existentes) — ou (rotulos, existentes, pausas) com `com_pausas`.

    Cada rotulo leva `dur`, a duracao lida em tempos de seminima.
    """
    glifos, textos, horiz, vert, formas, caminhos, beams = coletar(pg, com_ritmo=True)
    sistemas = pautas(horiz, pg.rect.width, pg.rect.height)
    if not any(g["tipo"] == "cabeca" for g in glifos) and sistemas:
        # PDF com os simbolos convertidos em curvas: le pela geometria
        glifos = glifos_de_contorno(caminhos, sistemas)
    rotulos, existentes, pausas = [], [], []

    centros = [(s[0] + s[-1]) / 2 for s in sistemas]

    def mais_proximo(y):
        return min(range(len(centros)), key=lambda i: abs(y - centros[i]))

    for sidx, linhas in enumerate(sistemas):
        topo, base_l = linhas[0], linhas[-1]
        span = base_l - topo

        def na_pauta(g, folga=2.6):
            return (mais_proximo(g["y"]) == sidx
                    and topo - folga * span < g["y"] < base_l + folga * span)

        cabecas = sorted([g for g in glifos if g["tipo"] == "cabeca" and na_pauta(g)],
                         key=lambda g: (g["x"], g["y"]))
        if not cabecas:
            continue
        # Mesma cabeca desenhada DUAS vezes no mesmo ponto: ha edicoes que poem uma
        # cabeca vazada por cima da preta para abrir o buraco onde vai o nome da nota.
        # E uma nota so — e a figura e a preta, nao a vazada.
        unicas = []
        for h in cabecas:
            gemea = next((u for u in unicas
                          if abs(u["x"] - h["x"]) < 0.04 * span
                          and abs(u["y"] - h["y"]) < 0.08 * span), None)
            if gemea is None:
                unicas.append(h)
            elif (h.get("extra") or 1) < (gemea.get("extra") or 1):
                gemea.update(extra=h.get("extra"), vazia=h.get("vazia", False))
        cabecas = unicas

        claves = [g for g in glifos if g["tipo"] == "clave" and na_pauta(g, 1.4)]
        topo_ref = min(claves, key=lambda g: g["x"])["extra"] if claves else 38
        x_clave = min((g["x1"] for g in claves), default=topo - 999)

        alt_armadura, xs_armadura = armadura([g for g in glifos if na_pauta(g, 1.4)],
                                            linhas, x_clave, topo_ref, cabecas)

        acidentes = [g for g in glifos if g["tipo"] == "acc" and na_pauta(g)
                     and g["x"] not in xs_armadura]

        # barras de compasso: verticais que cobrem a pauta inteira e nao sao haste
        def eh_haste(v):
            return any(abs(h["x"] - v["x"]) < 0.35 * span
                       and (v["y0"] - 0.2 * span <= h["y"] <= v["y0"] + 0.45 * span
                            or v["y1"] - 0.45 * span <= h["y"] <= v["y1"] + 0.2 * span)
                       for h in cabecas)

        barras = sorted(v["x"] for v in vert
                        if v["y0"] <= topo + 0.2 * span and v["y1"] >= base_l - 0.2 * span
                        and v["h"] >= span * 0.9 and not eh_haste(v))

        descansos = sorted((g for g in glifos if g["tipo"] == "pausa" and na_pauta(g, 1.2)),
                           key=lambda g: g["x"])
        dur_de, dur_pausa = duracao_das(
            cabecas, descansos, vert, beams,
            [g for g in glifos if g["tipo"] == "bandeira" and na_pauta(g)],
            [g for g in glifos if g["tipo"] == "ponto" and na_pauta(g)],
            barras, span / 4.0)

        # ---- casa cada acidente com a cabeca mais proxima a sua DIREITA.
        # Amarrar no sentido acidente->nota (e nao nota->acidente) da atribuicao 1:1
        # e tolera folga zero em x, que e o normal nas fontes Sonata.
        acc_de = {}
        for a in sorted(acidentes, key=lambda a: a["x"]):
            cand = [h for h in cabecas
                    if -0.35 * span < h["x0"] - a["x1"] < 1.6 * span
                    and abs(a["y"] - h["y"]) < span * 0.22
                    and id(h) not in acc_de]
            if cand:
                acc_de[id(min(cand, key=lambda h: h["x0"]))] = a["extra"]

        # ---- altura de cada cabeca, com acidente valendo ate o fim do compasso
        estado, i_barra = {}, 0
        notas = []
        for h in cabecas:
            while i_barra < len(barras) and barras[i_barra] < h["x0"]:
                estado.clear()
                i_barra += 1
            idx = indice_diatonico(h["y"], linhas, topo_ref)
            letra = DIATONICAS[idx % 7]

            simbolo = acc_de.get(id(h))
            if simbolo:
                alt = '' if simbolo == 'n' else simbolo
                estado[idx] = alt
            elif idx in estado:
                alt = estado[idx]
            else:
                alt = alt_armadura.get(letra, '')
            notas.append((h, nome(idx, alt, sistema), idx, alt, i_barra))

        # ---- ligadura de valor: a segunda cabeca nao ganha nome, e a primeira
        # recebe "_" e a duracao das duas somadas. Sem isso, uma nota so segurada
        # sai como tres ataques ("G G G") e ensina errado.
        lig = ligaduras_de([c for c in caminhos
                            if topo - 3 * span < (c["y0"] + c["y1"]) / 2 < base_l + 3 * span],
                           notas, span / 4.0, descansos)
        segura = set(lig)
        somado = {}
        for j in sorted(lig):
            raiz = lig[j]
            while raiz in lig:
                raiz = lig[raiz]
            somado[raiz] = (somado.get(raiz, dur_de[id(notas[raiz][0])][0])
                            + dur_de[id(notas[j][0])][0])

        # ---- linha de base dos rotulos: logo abaixo da tinta DESTE sistema.
        # So conta tinta abaixo da ultima linha da pauta, e ignora nomes de nota
        # ja escritos (senao a anotacao antiga do sistema de baixo empurra tudo).
        corpo = max(span * 0.40, 5.5)
        limite = min((s[0] for s in sistemas if s[0] > base_l + span), default=pg.rect.y1)
        # so olha a metade de cima do vao: mais abaixo ja e material do proximo sistema
        # (o colchete de casa 1a/2a fica logo acima da pauta seguinte).
        fundo = base_l + 0.45 * (limite - base_l)
        piso = base_l + span * 0.25
        # cabecas de nota abaixo da pauta (bbox de glifo tem altura de linha: usa o centro)
        for h in cabecas:
            if h["y"] > base_l:
                piso = max(piso, h["y"] + span * 0.32)
        # hastes / beams / ligaduras: desenho vetorial tem bbox justo
        for f in formas:
            if base_l < f["y1"] < fundo:
                piso = max(piso, f["y1"])
        for t in textos:
            cy = (t["bbox"][1] + t["bbox"][3]) / 2
            if base_l < cy < fundo and not RE_NOME_NOTA.match(t["txt"]):
                piso = max(piso, t["bbox"][3])
        y_base = max(piso + corpo * 1.15, base_l + span * 0.62)
        teto = limite - corpo * 0.35
        if y_base > teto:
            y_base = max(teto, base_l + span * 0.62)

        if com_pausas:
            i_barra = 0
            for g in descansos:
                while i_barra < len(barras) and barras[i_barra] < g["x0"]:
                    i_barra += 1
                pausas.append({"x": g["x"], "dur": dur_pausa[id(g)],
                               "sistema": sidx, "compasso": i_barra})

        for ordem, (h, txt, idx, alt, cmp_) in enumerate(notas):
            d, gr = dur_de.get(id(h), (1, False))
            total = somado.get(ordem, d)
            # A cabeca que so CONTINUA o som fica no relatorio (o compasso precisa da
            # duracao dela) mas com texto vazio: nao e estampada.
            preso = ordem in segura
            marca = "_" if (not gr and (ordem in somado or total >= 2)) else ""
            rotulos.append({"x": (h["x0"] + h["x1"]) / 2, "y_base": y_base,
                            "y_nota": h["y"], "corpo": corpo, "ordem": ordem,
                            "texto": "" if preso else txt + marca,
                            "nome": txt, "ligada": preso, "dur_total": total,
                            "idx": idx, "alt": alt, "midi": midi_de(idx, alt),
                            "dur": d, "graca": gr,
                            "sistema": sidx, "compasso": cmp_,
                            "armadura": (len(alt_armadura)
                                         * (1 if '#' in alt_armadura.values() else -1)
                                         if alt_armadura else 0)})

        # Nomes de nota que JA existem na partitura (candidatos a remocao).
        # Exige alinhamento com uma cabeca de nota: cifra de acorde solta no comeco
        # do compasso ("F", "Bb") nao entra.
        xs_cabeca = [(h["x0"] + h["x1"]) / 2 for h in cabecas]
        for t in textos:
            cx = (t["bbox"][0] + t["bbox"][2]) / 2
            cy = (t["bbox"][1] + t["bbox"][3]) / 2
            if (topo - 5.0 * span < cy < base_l + 2.6 * span and cx > x_clave
                    and "Chord" not in t["fonte"] and RE_NOME_NOTA.match(t["txt"])
                    and any(abs(cx - xh) < 1.1 * span for xh in xs_cabeca)):
                existentes.append(t)
    if com_pausas:
        return rotulos, existentes, pausas
    return rotulos, existentes


# ------------------------------------------------------------------- escrita
def escrever(pg, rotulos, cor):
    """Estampa os rotulos, empurrando para uma 2a fileira quando colidem."""
    FONTE = "helv"
    por_linha = {}
    for r in sorted((r for r in rotulos if r["texto"]),
                    key=lambda r: (r["y_base"], r["x"])):
        # O "_" de nota segurada corre PARA A DIREITA, sobre o espaco da cabeca que
        # nao recebeu nome. Se ele entrasse na largura, o nome sairia descentrado da
        # nota e ainda empurraria o rotulo para a segunda fileira sem necessidade.
        base = r["texto"].rstrip("_")
        cauda = r["texto"][len(base):]
        larg = fitz.get_text_length(base, fontname=FONTE, fontsize=r["corpo"])
        x0 = r["x"] - larg / 2
        fila, ocupado = 0, por_linha.setdefault(r["y_base"], {})
        while ocupado.get(fila, -1e9) > x0 - 0.08 * r["corpo"]:
            fila += 1
        ocupado[fila] = x0 + larg
        pg.insert_text((x0, r["y_base"] + fila * r["corpo"] * 1.05),
                       base + cauda, fontname=FONTE, fontsize=r["corpo"], color=cor)


def melodia(dados, limite=3000):
    """Sequencia tocavel: [{t, midi, d}] em tempos de seminima, na ordem de leitura.

    Cabecas no mesmo x sao um acorde: soam juntas e o tempo anda uma vez so. Pausa
    nao vira evento, so empurra o relogio. Apojatura recebe uma duracao simbolica —
    na pratica ela rouba tempo da nota seguinte, mas para ouvir a melodia basta ser
    rapida.
    """
    doc = fitz.open(stream=dados, filetype="pdf")
    ev, t = [], 0.0
    for pg in doc:
        rot, _, pausas = ler_notas(pg, "letras", com_pausas=True)
        itens = [{"x": r["x"], "s": r["sistema"], "midi": r["midi"],
                  "d": 0.125 if r["graca"] else r["dur_total"]}
                 for r in rot if not r["ligada"]]
        # a cabeca presa por ligadura nao e um ataque novo, mas o tempo dela tem de
        # passar: entra como "pausa" de duracao propria
        itens += [{"x": r["x"], "s": r["sistema"], "midi": None, "d": 0}
                  for r in rot if r["ligada"]]
        itens += [{"x": p["x"], "s": p["sistema"], "midi": None, "d": p["dur"]}
                  for p in pausas]
        itens.sort(key=lambda i: (i["s"], i["x"]))
        i = 0
        while i < len(itens) and len(ev) < limite:
            j = i
            while (j + 1 < len(itens) and itens[j + 1]["s"] == itens[i]["s"]
                   and abs(itens[j + 1]["x"] - itens[i]["x"]) < 1.0):
                j += 1
            grupo = itens[i:j + 1]
            passo = max(g["d"] for g in grupo) or 0.25
            for g in grupo:
                if g["midi"] is not None:
                    ev.append({"t": round(t, 4), "midi": g["midi"],
                               "d": round(g["d"] or 0.25, 4)})
            t += passo
            i = j + 1
    doc.close()
    return {"notas": ev, "total": round(t, 4)}


def anotar_bytes(dados, sistema="letras", limpar=False, cor=(0, 0, 0)):
    """Anota um PDF em memoria e devolve os bytes do PDF novo + um relatorio.

    Mesmo nucleo usado pela linha de comando; existe separado para a versao web,
    que nao tem sistema de arquivos.
    """
    doc = fitz.open(stream=dados, filetype="pdf")
    total, existentes_tot, limpos = 0, 0, 0
    por_pagina = []
    for pg in doc:
        rotulos, existentes = ler_notas(pg, sistema)
        existentes_tot += len(existentes)
        if limpar:
            fam = collections.Counter(familia(t["txt"]) for t in existentes)
            dominante = fam.most_common(1)[0][0] if fam else None
            alvos = [t for t in existentes if familia(t["txt"]) == dominante]
            if len(alvos) >= 0.5 * max(len(rotulos), 1):
                for t in alvos:
                    c = t["corpo"]
                    pg.draw_rect(fitz.Rect(t["x0"] - 0.5, t["base_y"] - 0.80 * c,
                                           t["x1"] + 0.5, t["base_y"] + 0.10 * c),
                                 color=None, fill=(1, 1, 1), width=0)
                limpos += len(alvos)
        escrever(pg, rotulos, cor)
        total += len(rotulos)
        por_pagina.append(len(rotulos))
    saida = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return saida, {"total": total, "por_pagina": por_pagina,
                   "existentes": existentes_tot, "limpos": limpos}


def main():
    ap = argparse.ArgumentParser(description="Escreve o nome das notas embaixo da pauta, no PDF original.")
    ap.add_argument("pdf")
    ap.add_argument("-o", "--out", default=None, help="PDF de saida (default: <nome>_notas.pdf)")
    ap.add_argument("--sistema", choices=["letras", "dore"], default="letras",
                    help="letras = C D E F G A B (default) | dore = Do Re Mi Fa Sol La Si")
    ap.add_argument("--limpar", action="store_true",
                    help="apaga os nomes de nota que ja existem na partitura")
    ap.add_argument("--cor", default="0,0,0", help="cor R,G,B em 0-1 (default preto)")
    a = ap.parse_args()

    cor = tuple(float(v) for v in a.cor.split(","))
    saida = a.out or os.path.splitext(a.pdf)[0] + "_notas.pdf"

    doc = fitz.open(a.pdf)
    total, achados_existentes, limpos = 0, 0, 0
    for pg in doc:
        rotulos, existentes = ler_notas(pg, a.sistema)
        achados_existentes += len(existentes)
        if a.limpar:
            # Duas travas para nao apagar cifra de acorde por engano:
            #  1) so limpa se houver nome para pelo menos metade das notas;
            #  2) so apaga a familia dominante — se a anotacao esta em Do-Re-Mi,
            #     um "F" solto na pagina e cifra e fica onde esta.
            fam = collections.Counter(familia(t["txt"]) for t in existentes)
            dominante = fam.most_common(1)[0][0] if fam else None
            alvos = [t for t in existentes if familia(t["txt"]) == dominante]
            if len(alvos) < 0.5 * max(len(rotulos), 1):
                print(f"  pagina {pg.number + 1}: --limpar ignorado "
                      f"({len(alvos)} nomes p/ {len(rotulos)} notas: parece cifra, nao anotacao)")
            else:
                existentes = alvos
                # Tarja branca justa a tinta. O bbox do span tem altura de linha inteira;
                # usar ele cortaria ligaduras que passam por cima da pauta.
                for t in existentes:
                    c = t["corpo"]
                    pg.draw_rect(fitz.Rect(t["x0"] - 0.5, t["base_y"] - 0.80 * c,
                                           t["x1"] + 0.5, t["base_y"] + 0.10 * c),
                                 color=None, fill=(1, 1, 1), width=0)
                limpos += len(existentes)
        escrever(pg, rotulos, cor)
        total += len(rotulos)
        print(f"  pagina {pg.number + 1}: {len(rotulos)} notas")

    if limpos:
        print(f"[limpar] {limpos} nomes antigos cobertos")
    if achados_existentes and not a.limpar:
        print(f"\n[aviso] a partitura ja tem {achados_existentes} nomes de nota escritos. "
              f"Use --limpar para apagar os antigos.")
    doc.save(saida, garbage=3, deflate=True)
    print(f"\n{total} notas anotadas -> {saida}")
    if total == 0:
        print("[erro] nenhuma nota encontrada: o PDF provavelmente e um scan (imagem), "
              "nao um export vetorial do MuseScore.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
