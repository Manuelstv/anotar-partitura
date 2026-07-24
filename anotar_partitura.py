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
PERFIS = {
    "smufl": {
        "cabecas": {0xE0A0, 0xE0A1, 0xE0A2, 0xE0A3, 0xE0A4},
        "acidentes": {0xE260: 'b', 0xE261: 'n', 0xE262: '#', 0xE263: '##', 0xE264: 'bb'},
        "claves": {0xE050: 38, 0xE051: 38, 0xE052: 38, 0xE053: 38, 0xE054: 38,
                   0xE062: 26, 0xE063: 26, 0xE064: 26, 0xE065: 26, 0xE05C: 32},
    },
    "sonata": {
        # confirmados nos PDFs de teste: 'oe'=cabeca preta, ponto=branca, w=semibreve,
        # &=clave de sol (aparece 1x por pauta), #/b/n=acidentes.
        "cabecas": {0x153, 0x2D9, 0x77},
        "acidentes": {0x62: 'b', 0x6E: 'n', 0x23: '#'},
        "claves": {0x26: 38, 0x3F: 26, 0x42: 32},   # sol confirmado; fa/do pelo layout Sonata
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


def coletar(pg):
    """Glifos musicais, spans de texto comum, linhas horizontais e verticais."""
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
                            tipo, extra = "cabeca", None
                        elif cp in P["acidentes"]:
                            tipo, extra = "acc", P["acidentes"][cp]
                        elif cp in P["claves"]:
                            tipo, extra = "clave", P["claves"][cp]
                        else:
                            continue
                        glifos.append({"tipo": tipo, "extra": extra,
                                       "x": (bb[0] + bb[2]) / 2,
                                       "y": (bb[1] + bb[3]) / 2 + ajuste,
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

    horiz, vert, formas = [], [], []
    for p in pg.get_drawings():
        r = p["rect"]
        if r.height < 250 * k and r.width < 250 * k:   # hastes, beams, ligaduras, colchetes
            formas.append({"x": (r.x0 + r.x1) / 2, "y": (r.y0 + r.y1) / 2,
                           "x0": r.x0, "x1": r.x1, "y0": r.y0, "y1": r.y1})
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
    return glifos, textos, horiz, vert, formas


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
    cand = [(y, _cobertura(segs)) for y, segs in niveis.items()]
    if not cand:
        return []

    # junta niveis quase coincidentes (mesma linha desenhada em duas passadas)
    cand.sort()
    k = altura_pagina / 842.0
    junta_max = 1.2 * k
    juntos = []
    for y, c in cand:
        if juntos and y - juntos[-1][0] < junta_max:
            y0, c0 = juntos[-1]
            juntos[-1] = ((y0 * c0 + y * c) / (c0 + c) if c0 + c else y0, c0 + c)
        else:
            juntos.append((y, c))

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
    usados, achadas = set(), []
    for i, (y, _) in enumerate(longas):
        if i in usados:
            continue
        linhas, idx = [y], [i]
        for m in range(1, 5):
            alvo = y + m * d
            melhor = None
            for j in range(i + 1, len(longas)):
                if j in usados or abs(ys[j] - alvo) > tol:
                    continue
                if melhor is None or (longas[j][1], -abs(ys[j] - alvo)) > \
                        (longas[melhor][1], -abs(ys[melhor] - alvo)):
                    melhor = j
            if melhor is None:
                break
            linhas.append(ys[melhor])
            idx.append(melhor)
        if len(linhas) == 5:
            achadas.append(linhas)
            usados.update(idx)
    return achadas


# ------------------------------------------------------------------- alturas
def indice_diatonico(cy, linhas, topo_ref):
    """Posicao vertical -> indice diatonico (C0 == 0)."""
    span = linhas[-1] - linhas[0]
    meio_espaco = span / 8.0
    passos = round((linhas[0] - cy) / meio_espaco)
    return topo_ref + passos


def armadura(glifos, linhas, x_clave, x_primeira_nota):
    """Conta sustenidos/bemois entre a clave e a primeira nota -> alteracoes por letra."""
    span = linhas[-1] - linhas[0]
    entre = [g for g in glifos
             if g["tipo"] == "acc" and g["extra"] in ('#', 'b')
             and x_clave < g["x"] < x_primeira_nota - 0.2 * span]
    s = sum(1 for g in entre if g["extra"] == '#')
    b = sum(1 for g in entre if g["extra"] == 'b')
    if s and s <= 7:
        return {n: '#' for n in ORDEM_SUSTENIDOS[:s]}, {g["x"] for g in entre}
    if b and b <= 7:
        return {n: 'b' for n in ORDEM_BEMOIS[:b]}, {g["x"] for g in entre}
    return {}, set()


def nome(idx, alt, sistema):
    letra = DIATONICAS[idx % 7]
    base = SOLFEJO[letra] if sistema == 'dore' else letra
    return base + alt


# --------------------------------------------------------------------- leitura
def ler_notas(pg, sistema):
    """Retorna (rotulos, existentes). rotulos = [{x, y_base, texto, ordem}]."""
    glifos, textos, horiz, vert, formas = coletar(pg)
    sistemas = pautas(horiz, pg.rect.width, pg.rect.height)
    rotulos, existentes = [], []

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

        claves = [g for g in glifos if g["tipo"] == "clave" and na_pauta(g, 1.4)]
        topo_ref = min(claves, key=lambda g: g["x"])["extra"] if claves else 38
        x_clave = min((g["x1"] for g in claves), default=topo - 999)

        x_primeira = min(g["x0"] for g in cabecas)
        alt_armadura, xs_armadura = armadura([g for g in glifos if na_pauta(g, 1.4)],
                                            linhas, x_clave, x_primeira)

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
            notas.append((h, nome(idx, alt, sistema)))

        # ---- linha de base dos rotulos: logo abaixo da tinta DESTE sistema.
        # So conta tinta abaixo da ultima linha da pauta, e ignora nomes de nota
        # ja escritos (senao a anotacao antiga do sistema de baixo empurra tudo).
        corpo = max(span * 0.34, 5.0)
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

        for ordem, (h, txt) in enumerate(notas):
            rotulos.append({"x": (h["x0"] + h["x1"]) / 2, "y_base": y_base,
                            "y_nota": h["y"], "texto": txt, "corpo": corpo, "ordem": ordem})

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
    return rotulos, existentes


# ------------------------------------------------------------------- escrita
def escrever(pg, rotulos, cor):
    """Estampa os rotulos, empurrando para uma 2a fileira quando colidem."""
    FONTE = "helv"
    por_linha = {}
    for r in sorted(rotulos, key=lambda r: (r["y_base"], r["x"])):
        larg = fitz.get_text_length(r["texto"], fontname=FONTE, fontsize=r["corpo"])
        x0 = r["x"] - larg / 2
        fila, ocupado = 0, por_linha.setdefault(r["y_base"], {})
        while ocupado.get(fila, -1e9) > x0 - 0.08 * r["corpo"]:
            fila += 1
        ocupado[fila] = x0 + larg
        pg.insert_text((x0, r["y_base"] + fila * r["corpo"] * 1.05),
                       r["texto"], fontname=FONTE, fontsize=r["corpo"], color=cor)


def anotar_bytes(dados, sistema="letras", limpar=False, cor=(0, 0, 0.75)):
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
    ap.add_argument("--cor", default="0,0,0.75", help="cor R,G,B em 0-1 (default azul escuro)")
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
