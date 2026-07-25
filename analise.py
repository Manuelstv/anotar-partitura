#!/usr/bin/env python3
"""Analise musical DETERMINISTICA de uma partitura em PDF.

Nada aqui e inferido por IA: tudo sai de teoria musical aplicada ao que foi de fato
lido do PDF. Isso importa num material de estudo — a analise nao pode inventar.

  tom       - a armadura ja da a colecao de notas; a duvida e so maior x relativa
              menor, resolvida por peso das tonicas no histograma e pela nota final.
  cifras    - na maioria das partituras a cifra ESTA no PDF como texto. Nao e preciso
              inferir harmonia: da para ler. Sao pegas acima da pauta, por regex.
  escalas   - de cada cifra sai a escala que cabe pra improvisar (tabela padrao).
  forma     - compassos com a mesma sequencia de alturas viram a mesma letra (A, B...).
  dificil   - dificuldade por compasso, para apontar onde a musica pesa.

Uso:  uv run analise.py <pdf>
"""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pymupdf
import anotar_partitura as A

CLASSES = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']
MAIOR_POR_SUST = ['C', 'G', 'D', 'A', 'E', 'B', 'F#', 'C#']
MAIOR_POR_BEMOL = ['C', 'F', 'Bb', 'Eb', 'Ab', 'Db', 'Gb', 'Cb']

# cifra: fundamental + qualidade + extensao + baixo. "N.C." = sem acorde.
RE_CIFRA = re.compile(
    r'^(N\.?C\.?|[A-G][#b]?(?:maj|Maj|MAJ|min|m|M|dim|aug|sus|\+|-|°|ø|Δ)?'
    r'(?:\d{1,2})?(?:\([^)]{0,8}\))?(?:sus\d?)?(?:add\d{1,2})?(?:/[A-G][#b]?)?)$')

# Qualidade da cifra -> escala que cabe por cima. A ORDEM importa: numero solto
# (9, 11, 13) sem "add"/"maj" ja implica setima menor, ou seja, e dominante.
ESCALAS = [
    (r'm7b5|\u00f8', 'lócrio (meio-diminuto)'),
    (r'dim|\u00b0', 'diminuta (tom-semitom)'),
    (r'7?sus', 'mixolídio sus4'),
    (r'7(alt|#9|b9|#5|b13)', 'alterada'),
    (r'maj|\u0394', 'jônio (maior)'),
    (r'^[A-G][#b]?(m|min)(?!aj)', 'dórico (menor)'),
    (r'add|^[A-G][#b]?6', 'jônio (maior)'),
    (r'7|9|11|13', 'mixolídio'),
]


def escala_da_cifra(cifra):
    for padrao, nome in ESCALAS:
        if re.search(padrao, cifra):
            return nome
    return 'jônio (maior)'


# --------------------------------------------------------- soletrar acorde
# Cada grau e (semitons, passo diatonico). O passo e o que decide a LETRA; o acidente
# sai da diferenca para o semitom alvo. Sem isso, C7 sairia "A#" em vez de "Bb".
LETRAS = ['C', 'D', 'E', 'F', 'G', 'A', 'B']
SEMI_LETRA = [0, 2, 4, 5, 7, 9, 11]
TRIADE = {
    'maj':  [(0, 0), (4, 2), (7, 4)],
    'min':  [(0, 0), (3, 2), (7, 4)],
    'dim':  [(0, 0), (3, 2), (6, 4)],
    'aug':  [(0, 0), (4, 2), (8, 4)],
    'sus4': [(0, 0), (5, 3), (7, 4)],
    'sus2': [(0, 0), (2, 1), (7, 4)],
}


def _classe(nome):
    """Nome de nota -> classe de altura (C=0). Usada pela deteccao de tom."""
    i = LETRAS.index(nome[0].upper()) if nome[:1].upper() in LETRAS else None
    if i is None:
        return None
    acc = 1 if nome[1:2] == '#' else (-1 if nome[1:2] == 'b' else 0)
    return (SEMI_LETRA[i] + acc) % 12


def _nome_grau(i_raiz, acc_raiz, semitons, passo):
    """Letra pelo passo diatonico; acidente pela distancia ate o semitom alvo."""
    li = (i_raiz + passo) % 7
    oit = (i_raiz + passo) // 7
    natural = SEMI_LETRA[li] + 12 * oit
    alvo = SEMI_LETRA[i_raiz] + acc_raiz + semitons
    acc = alvo - natural
    if abs(acc) > 1:          # dobrado (Sibb do dim7): o musico le o enarmonico
        return None
    return LETRAS[li] + ('#' * acc if acc > 0 else 'b' * -acc)


def soletrar(cifra):
    """'G7' -> ['G','B','D','F']. So teoria: nada e inferido por IA."""
    m = re.match(r'^([A-G])([#b]?)(.*)$', cifra)
    if not m:
        return []
    i_raiz = LETRAS.index(m.group(1))
    acc_raiz = {'#': 1, 'b': -1, '': 0}[m.group(2)]
    resto = m.group(3)
    baixo = None
    if '/' in resto:
        resto, baixo = resto.split('/', 1)
        baixo = baixo.strip()
    r = resto.replace('Maj', 'maj').replace('MAJ', 'maj').replace('\u0394', 'maj7')

    if re.search(r'm7b5|\u00f8', r):
        graus, r = [(0, 0), (3, 2), (6, 4), (10, 6)], re.sub(r'm7b5|\u00f8', '', r)
    elif re.search(r'dim7|\u00b07', r):
        graus, r = [(0, 0), (3, 2), (6, 4), (9, 6)], re.sub(r'dim7|\u00b07', '', r)
    elif re.search(r'dim|\u00b0', r):
        graus, r = list(TRIADE['dim']), re.sub(r'dim|\u00b0', '', r)
    elif re.search(r'aug|\+', r):
        graus, r = list(TRIADE['aug']), re.sub(r'aug|\+', '', r)
    elif 'sus2' in r:
        graus, r = list(TRIADE['sus2']), r.replace('sus2', '')
    elif 'sus' in r:
        graus, r = list(TRIADE['sus4']), re.sub(r'sus4?', '', r)
    elif re.match(r'^(m|min)(?!aj)', r):
        graus, r = list(TRIADE['min']), re.sub(r'^(m|min)', '', r)
    else:
        graus = list(TRIADE['maj'])

    tem_setima = any(g[1] == 6 for g in graus)
    if 'maj7' in r or 'maj9' in r:
        graus.append((11, 6))
    elif (not tem_setima and re.search(r'7|9|11|13', r)
            and 'add' not in r and not re.search(r'^6', r)):
        graus.append((10, 6))      # "add9" e "6/9" NAO levam setima
    if re.search(r'(^|[^1])6', r):
        graus.append((9, 5))
    if 'b9' in r:
        graus.append((13, 8))
    elif '#9' in r:
        graus.append((15, 8))
    elif '9' in r:
        graus.append((14, 8))
    if '#11' in r:
        graus.append((18, 10))
    elif '11' in r:
        graus.append((17, 10))
    if 'b13' in r:
        graus.append((20, 12))
    elif '13' in r:
        graus.append((21, 12))
    if 'b5' in r:
        graus = [(6, 4) if g == (7, 4) else g for g in graus]
    if '#5' in r:
        graus = [(8, 4) if g == (7, 4) else g for g in graus]

    todos = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']
    pc_raiz = (SEMI_LETRA[i_raiz] + acc_raiz) % 12
    notas = []
    for st, passo in sorted(dict.fromkeys(graus)):
        n = _nome_grau(i_raiz, acc_raiz, st, passo) or todos[(pc_raiz + st) % 12]
        if n not in notas:
            notas.append(n)
    if baixo and baixo not in notas:
        notas.append(baixo + " (baixo)")
    return notas


def ler_cifras(pg, sistemas, textos, formas):
    """Cifras que estao ACIMA de alguma pauta, em ordem de leitura.

    Marca de ensaio ("A", "B") tambem casa com a regex de cifra, mas vem dentro de uma
    CAIXA desenhada — e isso que separa as duas. Alem disso, se quase tudo que sobrou
    for letra pelada e forem poucas, sao secoes, nao harmonia.
    """
    def em_caixa(t):
        for f in formas:
            if (f["x0"] <= t["x0"] + 1 and f["x1"] >= t["x1"] - 1
                    and f["y0"] <= t["bbox"][1] + 1 and f["y1"] >= t["bbox"][3] - 1
                    and (f["x1"] - f["x0"]) < 4 * max(1.0, t["x1"] - t["x0"])):
                return True
        return False

    # Junta o SUFIXO de volta: a qualidade vem em span separado, tanto em sobrescrito
    # ("G" + "7") quanto em letras ("A" + "maj7", "A" + "m11"). Sem juntar, Amaj7 vira
    # "A" e a analise erra o acorde inteiro.
    acima = []
    for t in textos:
        cy = (t["bbox"][1] + t["bbox"][3]) / 2
        for i, sis in enumerate(sistemas):
            span = sis[-1] - sis[0]
            # o teto e a pauta ANTERIOR: senao o nome de nota escrito embaixo do sistema
            # de cima cai na faixa "acima" deste e vira cifra.
            # teto = meio do vao ate a pauta anterior. O nome de nota fica logo ABAIXO
            # dela (~0.6 span) e a cifra logo ACIMA desta (~1-2 span): o meio separa.
            anterior = sistemas[i - 1][-1] if i else 0
            teto = max(sis[0] - 2.6 * span, (anterior + sis[0]) / 2 if i else 0)
            if teto < cy < sis[0]:
                acima.append({"s": i, "txt": t["txt"].strip(), "x0": t["x0"],
                              "x1": t["x1"], "bbox": t["bbox"], "span": span})
                break
    acima.sort(key=lambda t: (t["s"], t["x0"]))
    juntos = []
    for t in acima:
        # sufixo = qualidade/extensao ("maj7", "m11", "7") ou o baixo de barra ("/C")
        eh_sufixo = bool(re.fullmatch(
            r'(maj|Maj|MAJ|min|m|M|dim|aug|sus|add|\u00b0|\u00f8|\u0394)?[\d#b()+\-]*'
            r'(/[A-G][#b]?)?', t["txt"])) and 0 < len(t["txt"]) <= 7
        # o acumulado pode ja ter sufixo: "G"+"add9"+"/C" -> "Gadd9/C"
        em_curso = juntos and re.fullmatch(r'[A-G][#b]?[A-Za-z0-9#b()+\-]{0,7}',
                                           juntos[-1]["txt"])
        if (juntos and juntos[-1]["s"] == t["s"] and eh_sufixo and em_curso
                and 0 <= t["x0"] - juntos[-1]["x1"] < 0.25 * t["span"]):
            juntos[-1]["txt"] += t["txt"]
            juntos[-1]["x1"] = t["x1"]
            continue
        juntos.append(dict(t))

    achadas = []
    for t in juntos:
        txt = t["txt"]
        if not RE_CIFRA.match(txt) or len(txt) > 10 or em_caixa(t):
            continue
        achadas.append((t["s"], (t["x0"] + t["x1"]) / 2, txt))
    achadas.sort()
    # uma cifra por posicao (o PDF as vezes duplica a camada de texto)
    limpo = []
    for sis, x, txt in achadas:
        if limpo and limpo[-1][0] == sis and abs(limpo[-1][1] - x) < 3 and limpo[-1][2] == txt:
            continue
        limpo.append((sis, x, txt))
    seq = [c[2] for c in limpo]
    reais = [c for c in seq if not c.startswith("N")]
    peladas = [c for c in reais if re.fullmatch(r'[A-G]', c)]
    if reais and len(peladas) >= 0.6 * len(reais) and len(set(reais)) <= 6:
        return []            # letra pelada e poucas: secao/ensaio, nao cifra
    return seq


def detectar_tom(notas, armadura):
    """Armadura da a colecao; o histograma decide entre maior e a relativa menor."""
    if armadura >= 0:
        maior = MAIOR_POR_SUST[min(armadura, 7)]
    else:
        maior = MAIOR_POR_BEMOL[min(-armadura, 7)]
    pc_maior = _classe(maior)
    pc_menor = (pc_maior + 9) % 12
    hist = collections.Counter(m % 12 for m in notas)
    total = sum(hist.values()) or 1
    # peso da tonica: quanto a nota aparece + se a musica termina nela
    peso_maior = hist[pc_maior] / total + (0.25 if notas and notas[-1] % 12 == pc_maior else 0)
    peso_menor = hist[pc_menor] / total + (0.25 if notas and notas[-1] % 12 == pc_menor else 0)
    menor = CLASSES[pc_menor]
    if peso_menor > peso_maior:
        return f"{menor} menor", f"{maior} maior", armadura
    return f"{maior} maior", f"{menor} menor", armadura


def forma(compassos):
    """Compassos com a mesma sequencia de alturas recebem a mesma letra."""
    vistos, letras, seq = {}, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", []
    for c in compassos:
        chave = tuple(c)
        if chave not in vistos:
            vistos[chave] = seq and letras[len(vistos) % 26] or 'A'
            vistos[chave] = letras[(len(vistos) - 1) % 26]
        seq.append(vistos[chave])
    return ''.join(seq)


def analisar(dados):
    """Recebe bytes de PDF, devolve um dicionario de fatos medidos."""
    doc = pymupdf.open(stream=dados, filetype="pdf")
    notas, cifras, compassos = [], [], {}
    for pg in doc:
        glifos, textos, horiz, vert, formas, caminhos = A.coletar(pg)
        sistemas = A.pautas(horiz, pg.rect.width, pg.rect.height)
        rot, _ = A.ler_notas(pg, "letras")
        cifras += ler_cifras(pg, sistemas, textos, formas)
        for r in sorted(rot, key=lambda r: (r["sistema"], r["x"])):
            notas.append(r)
            compassos.setdefault((pg.number, r["sistema"], r["compasso"]), []).append(r)
    doc.close()
    if not notas:
        return None

    midis = [r["midi"] for r in notas]
    arm = collections.Counter(r["armadura"] for r in notas).most_common(1)[0][0]
    tom, relativa, _ = detectar_tom(midis, arm)

    # compassos mais dificeis: extensao + saltos + alteracoes dentro do compasso
    dif = []
    for chave, rs in compassos.items():
        if len(rs) < 2:
            continue
        ms = [r["midi"] for r in rs]
        saltos = [abs(b - a) for a, b in zip(ms, ms[1:])]
        pontos = (max(ms) - min(ms)) * 0.25 + max(saltos) * 0.5 \
            + sum(1 for r in rs if r["alt"]) * 1.2 + len(rs) * 0.2 \
            + sum(1 for m in ms if m >= 84) * 1.5
        motivos = []
        if max(saltos) >= 9:
            motivos.append(f"salto de {max(saltos)} semitons")
        if any(m >= 84 for m in ms):
            motivos.append("agudo de chave de palma")
        if any(m <= 61 for m in ms):
            motivos.append("grave de mindinho")
        n_alt = sum(1 for r in rs if r["alt"])
        if n_alt >= 2:
            motivos.append(f"{n_alt} notas alteradas")
        if len(rs) >= 8:
            motivos.append(f"{len(rs)} notas no compasso")
        dif.append({"pagina": chave[0] + 1, "sistema": chave[1] + 1,
                    "notas": len(rs), "pontos": round(pontos, 1),
                    "motivos": motivos or ["nada de especial"]})
    dif.sort(key=lambda d: -d["pontos"])

    freq = collections.Counter(r["texto"] for r in notas)
    seq_comp = [tuple(r["midi"] for r in v) for v in compassos.values()]
    unicos = len(set(seq_comp))

    cifras_unicas = list(dict.fromkeys(c for c in cifras if not c.startswith("N")))
    return {
        "n_notas": len(notas),
        "tom": tom,
        "tom_relativo": relativa,
        "armadura": arm,
        "grave": CLASSES[min(midis) % 12] + str(min(midis) // 12 - 1),
        "agudo": CLASSES[max(midis) % 12] + str(max(midis) // 12 - 1),
        "extensao": max(midis) - min(midis),
        "frac_alteradas": round(sum(1 for r in notas if r["alt"]) / len(notas), 3),
        "mais_tocadas": freq.most_common(5),
        "cifras": cifras_unicas,
        "progressao": cifras[:24],
        "escalas": [{"cifra": c, "escala": escala_da_cifra(c), "notas": soletrar(c)}
                    for c in cifras_unicas[:14]],
        "compassos": len(compassos),
        "compassos_distintos": unicos,
        "repeticao": round(1 - unicos / max(1, len(compassos)), 2),
        "dificeis": dif[:3],
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    r = analisar(open(sys.argv[1], "rb").read())
    if not r:
        print("nenhuma nota legivel")
        return 1
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
