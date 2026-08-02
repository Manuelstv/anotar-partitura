#!/usr/bin/env python3
"""Analise musical DETERMINISTICA de uma partitura em PDF.

Nada aqui e inferido por IA: tudo sai de teoria musical aplicada ao que foi de fato
lido do PDF. Isso importa num material de estudo — a analise nao pode inventar.

  tom       - a armadura ja da a colecao de notas; a duvida e so maior x relativa
              menor, resolvida por peso das tonicas no histograma e pela nota final.
  cifras    - na maioria das partituras a cifra ESTA no PDF como texto. Nao e preciso
              inferir harmonia: da para ler. Sao pegas acima da pauta, por regex.
  escalas   - de cada cifra sai a escala que cabe pra improvisar (tabela padrao).
  funcional - cada cifra vira grau romano no tom, e sequencia por quartas vira ii-V-I.
              E o que diz onde UMA escala serve para tres acordes.
  campo     - as sete TETRADES do tom, com o modo de cada grau.
  real      - sax alto e em Eb: o som real fica uma sexta maior abaixo do escrito, e a
              armadura de concerto = a escrita - 3 bemois. Aritmetica, nao tabela.
  ritmo     - formula pela soma MODAL dos compassos, figuras, sincope e densidade.
  respiro   - pausa ou nota longa dizem onde da para respirar; frase longa vira aviso.
  motivos   - o mesmo desenho de intervalos repetido, ainda que transposto.
  forma     - compassos com a mesma sequencia de alturas viram a mesma letra (A, B...).
  dificil   - dificuldade por compasso, para apontar onde a musica pesa.
  folha     - `folha_de_cifras` gera um PDF novo so com a harmonia, um quadro por compasso.

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
POR_BEMOL = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B']
POR_SUST = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# os sete modos na ordem dos graus da escala maior
MODOS = ['jônio (maior)', 'dórico', 'frígio', 'lídio', 'mixolídio',
         'eólio (menor)', 'lócrio']
NUMERAIS = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII']

# Tetrade pelos TRES intervalos consecutivos (3a, 3a, 3a) -> sufixo de cifra, sufixo do
# grau romano, nome. Derivar disso, e nao de tabela por grau, e o que faz o campo
# harmonico sair certo em qualquer tom e em qualquer modo.
TETRADE = {
    (4, 3, 4): ('maj7', 'maj7', 'maior com sétima maior'),
    (4, 3, 3): ('7', '7', 'dominante'),
    (3, 4, 3): ('m7', '7', 'menor com sétima'),
    (3, 3, 4): ('m7b5', '7b5', 'meio-diminuto'),
    (3, 3, 3): ('dim7', '°7', 'diminuto'),
    (3, 4, 4): ('mMaj7', 'maj7', 'menor com sétima maior'),
    (4, 4, 3): ('maj7#5', 'maj7#5', 'aumentado com sétima maior'),
}
# tipos cuja terca e menor: o grau romano vai em minuscula
TIPOS_MENORES = {'m7', 'm7b5', 'dim7', 'dim', 'min', 'mMaj7'}
SUFIXO_GRAU = {'maj7': 'maj7', '7': '7', 'm7': '7', 'm7b5': '7b5', 'dim7': '°7',
               'dim': '°', 'min': '', 'maj': '', 'aug': '+', 'mMaj7': 'maj7',
               '6': '6', 'sus': 'sus'}
TIPOS_TONICA_MAIOR = {'maj', 'maj7', '6'}
TIPOS_TONICA_MENOR = {'min', 'm7', 'mMaj7'}

# soma do compasso em tempos de seminima -> formula. 3.0 e ambiguo de proposito:
# 6/8 tambem soma tres seminimas, e nao ha como separar sem ler a formula desenhada.
FORMULAS = {1.5: '3/8', 2.0: '2/4', 2.5: '5/8', 3.0: '3/4 (ou 6/8)', 3.5: '7/8',
            4.0: '4/4', 4.5: '9/8', 5.0: '5/4', 6.0: '6/4 (ou 12/8)', 7.0: '7/4',
            8.0: '4/2'}
FIGURAS = {8.0: 'breve', 6.0: 'semibreve pontuada', 4.0: 'semibreve',
           3.0: 'mínima pontuada', 2.0: 'mínima', 1.5: 'semínima pontuada',
           1.0: 'semínima', 0.75: 'colcheia pontuada', 0.5: 'colcheia',
           0.375: 'semicolcheia pontuada', 0.25: 'semicolcheia', 0.125: 'fusa',
           0.0625: 'semifusa'}

# Sax alto: instrumento em Eb, soa uma SEXTA MAIOR abaixo do escrito (9 semitons).
TRANSPOSICAO_ALTO = -9

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


def graus_da_cifra(cifra):
    """'G7' -> (indice de G, 0, [(0,0),(4,2),(7,4),(10,6)], baixo).

    Cada grau e (semitons, passo diatonico). Quem quer as NOTAS chama `soletrar`; quem
    quer a QUALIDADE chama `tipo_da_cifra`. As duas leem daqui, para nao existirem duas
    teorias diferentes no mesmo arquivo.
    """
    m = re.match(r'^([A-G])([#b]?)(.*)$', cifra)
    if not m:
        return None
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
    return i_raiz, acc_raiz, sorted(dict.fromkeys(graus)), baixo


def tipo_da_cifra(cifra):
    """(classe de altura da fundamental, tipo curto). Ex.: 'Dm7' -> (2, 'm7').

    O tipo sai dos INTERVALOS, nao do texto: 'Cmi7', 'Cm7' e 'C-7' caem no mesmo lugar.
    """
    g = graus_da_cifra(cifra)
    if not g:
        return None, None
    i_raiz, acc_raiz, graus, _ = g
    st = {passo: s for s, passo in graus}
    t3, q5, s7, s6 = st.get(2), st.get(4), st.get(6), st.get(5)
    if t3 is None:
        tipo = 'sus'
    elif t3 == 3:
        if q5 == 6:
            tipo = 'm7b5' if s7 == 10 else ('dim7' if s7 == 9 else 'dim')
        elif s7 == 11:
            tipo = 'mMaj7'
        elif s7 == 10:
            tipo = 'm7'
        else:
            tipo = 'min'
    elif q5 == 8:
        tipo = 'aug'
    elif s7 == 11:
        tipo = 'maj7'
    elif s7 == 10:
        tipo = '7'
    elif s6 == 9:
        tipo = '6'
    else:
        tipo = 'maj'
    return (SEMI_LETRA[i_raiz] + acc_raiz) % 12, tipo


def soletrar(cifra):
    """'G7' -> ['G','B','D','F']. So teoria: nada e inferido por IA."""
    g = graus_da_cifra(cifra)
    if not g:
        return []
    i_raiz, acc_raiz, graus, baixo = g
    todos = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']
    pc_raiz = (SEMI_LETRA[i_raiz] + acc_raiz) % 12
    notas = []
    for st, passo in graus:
        n = _nome_grau(i_raiz, acc_raiz, st, passo) or todos[(pc_raiz + st) % 12]
        if n not in notas:
            notas.append(n)
    if baixo and baixo not in notas:
        notas.append(baixo + " (baixo)")
    return notas


# A fonte de cifra do Sibelius (OpusChords*) escreve os simbolos em codepoints PROPRIOS:
# "A‹7" e Am7, "GŒ„Š7" e Gmaj7, "F©Ø7" e F#m7b5, "B¨" e Bb, "Fº" e Fdim. Sem traduzir, toda
# cifra que nao seja numerica (G7, C7) e descartada — e no acervo do Manuel, que e todo
# Sibelius, isso e a maioria das cifras. Medido em 59 PDFs: 662 "‹", 352 "Œ„Š", 255 "¨".
# A traducao vale SO para spans da fonte de cifra: em OpusStd os mesmos codepoints sao
# cabeca de nota e pausa (U+0152 e a pausa de seminima), e traduzir global estragaria isso.
GLIFOS_CIFRA = [('Œ„Š', 'maj'), ('‹', 'm'), ('¨', 'b'),
                ('©', '#'), ('Ø', 'ø'), ('º', '°')]


def _texto_de_cifra(txt, fonte):
    if 'Chord' not in (fonte or ''):
        return txt
    for de, para in GLIFOS_CIFRA:
        txt = txt.replace(de, para)
    return txt


# ------------------------------------------------- nome de nota em do-re-mi
# O botao "Do Re Mi" da entrada manda em TODA a analise, nao so no que e estampado na
# pauta: quem le "Lá" embaixo da nota nao quer ver "Am7" no cartao de acordes. A traducao
# e feita na SAIDA de `analisar`, num passe unico, para que a teoria toda continue
# trabalhando em letras — soletrar um acorde a partir de "Lá" seria reescrever tudo.
DORE = {'C': 'Dó', 'D': 'Ré', 'E': 'Mi', 'F': 'Fá', 'G': 'Sol', 'A': 'Lá', 'B': 'Si'}
RE_NOTA_SOLTA = re.compile(r'\b([A-G])([b#])?\b')


def _pt_nota(n):
    """'Bb' -> 'Sib'; 'F3' -> 'Fá3'; 'E menor' -> 'Mi menor'. So a primeira letra muda."""
    if not n or n[0] not in DORE:
        return n
    return DORE[n[0]] + n[1:]


def _pt_cifra(c):
    """'Am7' -> 'Lám7'; 'Gadd9/C' -> 'Soladd9/Dó'. O baixo de barra tambem traduz."""
    return '/'.join(_pt_nota(p) for p in c.split('/'))


def _pt_frase(t):
    """Nome de nota SOLTO dentro de uma frase ("G maior serve nos três").

    So pega letra isolada: "B7" fica intacto (nao ha fronteira de palavra entre B e 7) e a
    conjuncao "e" e minuscula, entao nunca vira nota.
    """
    return RE_NOTA_SOLTA.sub(lambda m: _pt_nota(m.group(0)), t) if t else t


def _traduzir(d):
    """Passa a saida de `analisar` para do-re-mi, campo por campo."""
    d["tom"] = _pt_nota(d["tom"])
    d["tom_relativo"] = _pt_nota(d["tom_relativo"])
    d["escala_do_tom"] = [_pt_nota(n) for n in d["escala_do_tom"]]
    d["grave"], d["agudo"] = _pt_nota(d["grave"]), _pt_nota(d["agudo"])
    if d.get("real"):
        for k in ("tom", "grave", "agudo"):
            d["real"][k] = _pt_nota(d["real"][k])
    d["mais_tocadas"] = [[_pt_nota(n), q] for n, q in d["mais_tocadas"]]
    d["fora_do_tom"] = [[_pt_nota(n), q] for n, q in d["fora_do_tom"]]
    d["cifras"] = [_pt_cifra(c) for c in d["cifras"]]
    d["progressao"] = [_pt_cifra(c) for c in d["progressao"]]
    for e in d["escalas"]:
        e["cifra"] = _pt_cifra(e["cifra"])
        e["notas"] = [_pt_nota(n.replace(" (baixo)", "")) + (" (baixo)" if "(baixo)" in n else "")
                      for n in e["notas"]]
    for it in d["funcional"]:
        it["cifra"] = _pt_cifra(it["cifra"])
    for c in d["cadencias"]:
        c["acordes"] = [_pt_cifra(a) for a in c["acordes"]]
        c["alvo"] = _pt_frase(c["alvo"])
        c["escala"] = _pt_frase(c["escala"])
    for g in d["campo"]:
        g["cifra"] = _pt_cifra(g["cifra"])
        g["triade"] = _pt_cifra(g["triade"])
        g["notas"] = [_pt_nota(n) for n in g["notas"]]
    for m in d["motivos"]:
        m["notas"] = [_pt_nota(n) for n in m["notas"]]
    for e in d.get("leitura", []):
        e["n"] = _pt_nota(e["n"])
    for linha in d["grade"]:
        for c in linha["cifras"]:
            c["cifra"] = _pt_cifra(c["cifra"])
    if d.get("blues"):
        d["blues"] = _pt_frase(d["blues"])
    return d


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
                acima.append({"s": i, "x0": t["x0"], "x1": t["x1"], "bbox": t["bbox"],
                              "span": span,
                              "txt": _texto_de_cifra(t["txt"].strip(), t.get("fonte"))})
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
    reais = [c[2] for c in limpo if not c[2].startswith("N")]
    peladas = [c for c in reais if re.fullmatch(r'[A-G]', c)]
    if reais and len(peladas) >= 0.6 * len(reais) and len(set(reais)) <= 6:
        return []            # letra pelada e poucas: secao/ensaio, nao cifra
    # Nome de nota escrito ACIMA da pauta (versao "With Note Names" do acervo, onde o
    # plugin usa a MESMA fonte da cifra) cai todo nesta faixa. O que separa e a densidade:
    # cifra vem uma por compasso, nome de nota vem uma por nota — medi 26 por sistema num
    # Take Five, contra 4 num lead sheet de verdade. E nenhum deles tem sufixo.
    sem_sufixo = [c for c in reais if re.fullmatch(r'[A-G][#b]?', c)]
    if reais and len(sem_sufixo) >= 0.9 * len(reais) \
            and len(reais) > 10 * max(1, len(sistemas)):
        return []
    # a POSICAO vai junto: e o que permite dizer em que compasso a cifra esta, e sem isso
    # nao ha grade de compassos para a folha de cifras
    return [{"cifra": txt, "sistema": sis, "x": x} for sis, x, txt in limpo]


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


def tom_pelas_cifras(seq, armadura):
    """Maior ou menor decidido pela HARMONIA. None quando o sinal nao e claro.

    A melodia sozinha nao separa Do maior de La menor: as duas tem as mesmas sete notas, e
    o histograma decide por pouco. A harmonia decide melhor — quem aparece como acorde de
    tonica e, sobretudo, qual acorde FECHA a musica, que e a definicao pratica de tom.
    """
    maior = (MAIOR_POR_SUST[min(armadura, 7)] if armadura >= 0
             else MAIOR_POR_BEMOL[min(-armadura, 7)])
    pc_maior = _classe(maior)
    pc_menor = (pc_maior + 9) % 12
    v_maior = v_menor = 0
    for i, c in enumerate(seq):
        pc, tipo = tipo_da_cifra(c)
        if pc is None:
            continue
        peso = 3 if i == len(seq) - 1 else 1        # o ultimo acorde vale por tres
        if pc == pc_maior and tipo in TIPOS_TONICA_MAIOR:
            v_maior += peso
        elif pc == pc_menor and tipo in TIPOS_TONICA_MENOR:
            v_menor += peso
    if abs(v_maior - v_menor) < 2:
        return None
    return 'maior' if v_maior > v_menor else 'menor'


# grau -> qualidade, pelas distancias em semitons dentro da triade
_QUAL = {(4, 3): ('', 'maior'), (3, 4): ('m', 'menor'),
         (3, 3): ('\u00b0', 'diminuto'), (4, 4): ('+', 'aumentado')}


def escala_do_tom(tonica, armadura):
    """[(nome, classe de altura)] das 7 notas do tom, a partir da tonica.

    Sao 7 LETRAS seguidas com a alteracao da armadura — nunca uma tabela de semitons.
    E o que faz Db maior sair "Db Eb F Gb Ab Bb C" e nao "C# D# ...".
    """
    i_ton = LETRAS.index(tonica[0])
    alt = {}
    if armadura > 0:
        alt = {n: 1 for n in A.ORDEM_SUSTENIDOS[:armadura]}
    elif armadura < 0:
        alt = {n: -1 for n in A.ORDEM_BEMOIS[:-armadura]}
    escala = []
    for g in range(7):
        li = (i_ton + g) % 7
        a = alt.get(LETRAS[li], 0)
        escala.append((LETRAS[li] + ('#' if a > 0 else 'b' if a < 0 else ''),
                       (SEMI_LETRA[li] + a) % 12))
    return escala


def campo_harmonico(tonica, modo, armadura):
    """As 7 TETRADES que cabem no tom, com o modo de cada grau.

    A triade responde "que acorde e"; a tetrade responde "o que eu toco por cima" — a
    setima e justamente a nota que separa Imaj7 de V7 e que decide a escala. Por isso o
    campo sai sempre em quatro notas, com a triade ao lado.

    Nao sao os acordes DA MUSICA — sao os que o tom comporta. Util quando a partitura
    nao traz cifra, que e o caso da maioria dos arranjos de banda.
    """
    escala = escala_do_tom(tonica, armadura)
    # eolio (menor natural) e o 6o modo do maior: por isso o giro de 5 no modo menor
    giro = 0 if modo == 'maior' else 5
    saida = []
    for g in range(7):
        nomes = [escala[(g + k) % 7][0] for k in (0, 2, 4, 6)]
        pcs = [escala[(g + k) % 7][1] for k in (0, 2, 4, 6)]
        t = tuple((pcs[k + 1] - pcs[k]) % 12 for k in range(3))
        suf_c, suf_g, qual = TETRADE.get(t, ('', '', 'maior'))
        suf3, qual3 = _QUAL.get(t[:2], ('', 'maior'))
        romano = NUMERAIS[g].lower() if t[0] == 3 else NUMERAIS[g]
        saida.append({"grau": romano + suf_g, "cifra": nomes[0] + suf_c,
                      "qualidade": qual, "notas": nomes,
                      "triade": nomes[0] + suf3, "triade_qual": qual3,
                      "modo": MODOS[(g + giro) % 7]})
    return saida


def romano_de(pc, escala, tipo):
    """Classe de altura -> grau romano dentro do tom ("ii7", "V7", "bVII7", "#IV7b5").

    Fora do tom o grau leva alteracao: prefere bemol (bIII, bVI, bVII), menos no tritom,
    que todo mundo le como #IV.
    """
    pcs = [p for _, p in escala]
    base, alt = None, ''
    if pc in pcs:
        base = pcs.index(pc)
    elif (pc - pcs[3]) % 12 == 1:                     # #IV, nunca bV
        base, alt = 3, '#'
    else:
        for g in range(7):
            if (pc - pcs[g]) % 12 == 11:
                base, alt = g, 'b'
                break
        else:
            for g in range(7):
                if (pc - pcs[g]) % 12 == 1:
                    base, alt = g, '#'
                    break
    if base is None:
        return '?'
    num = NUMERAIS[base]
    if tipo in TIPOS_MENORES:
        num = num.lower()
    return alt + num + SUFIXO_GRAU.get(tipo, '')


def _nomeador(armadura):
    """Como escrever uma classe de altura solta: bemol em tom de bemol, sustenido no resto."""
    tabela = POR_BEMOL if armadura <= 0 else POR_SUST
    return lambda pc: tabela[pc % 12]


def grau_de_cifra(cifra, escala):
    """'Dm7' em C -> 'ii7'. Vazio se o texto nao for cifra."""
    pc, tipo = tipo_da_cifra(cifra)
    return romano_de(pc, escala, tipo) if pc is not None else ''


def funcional(prog, tonica, modo, armadura):
    """Cada cifra vira GRAU no tom, e o grau diz o que ela esta fazendo ali.

    E a diferenca entre decorar sete acordes e entender um: Dm7 G7 Cmaj7 nao sao tres
    estudos, sao um ii-V-I, e uma escala so serve nos tres. `prog` e a lista de
    {cifra, compasso} na ordem de leitura.
    """
    escala = escala_do_tom(tonica, armadura)
    pcs = [p for _, p in escala]
    itens = []
    for c in prog:
        pc, tipo = tipo_da_cifra(c["cifra"])
        if pc is None:
            continue
        itens.append({"cifra": c["cifra"], "linha": c.get("linha"), "pc": pc,
                      "tipo": tipo, "grau": romano_de(pc, escala, tipo),
                      "dentro": pc in pcs, "papel": ""})
    # "G7 G7 C" e um V-I, nao dois: repeticao imediata do mesmo acorde colapsa
    seq = [it for i, it in enumerate(itens)
           if i == 0 or (it["pc"], it["tipo"]) != (itens[i - 1]["pc"], itens[i - 1]["tipo"])]
    for i, it in enumerate(seq):
        prox = seq[i + 1] if i + 1 < len(seq) else None
        # resolucao = fundamental subindo uma QUARTA (V->I). Em classes de altura, +5.
        resolve = prox is not None and (prox["pc"] - it["pc"]) % 12 == 5
        if it["tipo"] == '7':
            if it["pc"] == pcs[4]:
                it["papel"] = 'dominante do tom'
            elif resolve:
                it["papel"] = 'dominante de ' + romano_de(prox["pc"], escala, prox["tipo"])
            elif (it["pc"] - pcs[0]) % 12 == 1:
                it["papel"] = 'subV (substituto de trítono)'
            elif not it["dentro"]:
                it["papel"] = 'dominante emprestado'
        elif it["tipo"] in ('m7', 'm7b5', 'min') and prox is not None \
                and prox["tipo"] == '7' and resolve:
            it["papel"] = 'o ii de um ii-V'
        elif not it["dentro"]:
            it["papel"] = 'emprestado (fora do tom)'
    return seq


def cadencias(seq, armadura):
    """ii-V-I e V-I na sequencia: fundamental subindo de QUARTA com as qualidades certas.

    A busca e por classe de altura, nunca por nome de acorde — assim vale em qualquer tom
    e continua valendo num trecho que modula.
    """
    nome = _nomeador(armadura)

    def quarta(a, b):
        return b is not None and (b["pc"] - a["pc"]) % 12 == 5

    achadas, i, n = [], 0, len(seq)
    while i < n:
        a = seq[i]
        b = seq[i + 1] if i + 1 < n else None
        c = seq[i + 2] if i + 2 < n else None
        # cadeia de dominantes: cada um puxa o proximo por quarta (B7 E7 A7 D7). Vem antes
        # do V-I porque o alvo tambem e dominante, e o par isolado nao conta a historia.
        if a["tipo"] == '7':
            j = i
            while j + 1 < n and seq[j + 1]["tipo"] == '7' and quarta(seq[j], seq[j + 1]):
                j += 1
            if j - i >= 2:
                achadas.append({"nome": 'dominantes em cadeia',
                                "alvo": nome((seq[j]["pc"] + 5) % 12),
                                "acordes": [x["cifra"] for x in seq[i:j + 1]],
                                "linha": a["linha"],
                                "escala": 'mixolídio em cada um, ou a alterada para tensão'})
                i = j + 1
                continue
        if (a["tipo"] in ('m7', 'min') and b and b["tipo"] == '7' and quarta(a, b)
                and c and c["tipo"] in TIPOS_TONICA_MAIOR and quarta(b, c)):
            alvo = nome(c["pc"])
            achadas.append({"nome": 'ii-V-I', "alvo": alvo + ' maior',
                            "acordes": [a["cifra"], b["cifra"], c["cifra"]],
                            "linha": a["linha"],
                            "escala": f'{alvo} maior serve nos três'})
            i += 3
            continue
        if (a["tipo"] in ('m7b5', 'm7') and b and b["tipo"] == '7' and quarta(a, b)
                and c and c["tipo"] in TIPOS_TONICA_MENOR and quarta(b, c)):
            alvo = nome(c["pc"])
            achadas.append({"nome": 'ii-V-i', "alvo": alvo + ' menor',
                            "acordes": [a["cifra"], b["cifra"], c["cifra"]],
                            "linha": a["linha"],
                            "escala": f'{alvo} menor; no V7, {alvo} menor harmônica'})
            i += 3
            continue
        if a["tipo"] in ('m7', 'm7b5', 'min') and b and b["tipo"] == '7' and quarta(a, b):
            alvo = nome((b["pc"] + 5) % 12)
            achadas.append({"nome": 'ii-V', "alvo": alvo,
                            "acordes": [a["cifra"], b["cifra"]],
                            "linha": a["linha"],
                            "escala": f'mira {alvo} e não resolve'})
            i += 2
            continue
        if (a["tipo"] == '7' and b
                and b["tipo"] in TIPOS_TONICA_MAIOR | TIPOS_TONICA_MENOR and quarta(a, b)):
            alvo = nome(b["pc"])
            achadas.append({"nome": 'V-I', "alvo": alvo,
                            "acordes": [a["cifra"], b["cifra"]],
                            "linha": a["linha"],
                            "escala": f'{alvo} ' + ('maior' if b["tipo"]
                                                    in TIPOS_TONICA_MAIOR else 'menor')})
            i += 2
            continue
        i += 1
    return achadas


def e_blues(seq, tonica, armadura):
    """I7 com IV7 = blues, porque tonica dominante nao existe no campo maior.

    So isso da falso positivo: o Autumn Leaves tem E7 e A7 de passagem e caia aqui. Blues
    e dominante de ponta a ponta, entao exijo tambem que quase todo acorde seja dominante —
    um maj7 ou m7 de tonica no meio ja diz que a musica e outra coisa.
    """
    pcs = [p for _, p in escala_do_tom(tonica, armadura)]
    dom = {it["pc"] for it in seq if it["tipo"] == '7'}
    n_dom = sum(1 for it in seq if it["tipo"] == '7')
    if pcs[0] in dom and pcs[3] in dom and len(seq) >= 4 and n_dom >= 0.7 * len(seq):
        quinto = ' e V7' if pcs[4] in dom else ''
        return f'harmonia de blues: I7, IV7{quinto} — escala de blues em {tonica}'
    return None


def _tonica_por_armadura(arm, modo):
    if arm >= 0:
        maior = MAIOR_POR_SUST[min(arm, 7)]
    else:
        maior = MAIOR_POR_BEMOL[min(-arm, 7)]
    return maior if modo == 'maior' else CLASSES[(_classe(maior) + 9) % 12]


def som_real(tonica, modo, armadura, midis):
    """O que a plateia ouve: o sax alto soa uma SEXTA MAIOR abaixo do escrito.

    A armadura de concerto sai por aritmetica — a escrita menos 3 bemois — e nao por
    tabela. Se a conta cair fora do circulo de quintas, o nome vem do enarmonico simples,
    para nao inventar armadura de 10 bemois.
    """
    arm_real = armadura - 3
    pc_real = (_classe(tonica) + TRANSPOSICAO_ALTO) % 12
    nome = _tonica_por_armadura(arm_real, modo)
    if _classe(nome) != pc_real:                 # saiu do circulo: usa o enarmonico
        nome = POR_BEMOL[pc_real]
        arm_real = None
    dizer = _nomeador(arm_real if arm_real is not None else -1)
    reais = [m + TRANSPOSICAO_ALTO for m in midis]
    return {"tom": f'{nome} {modo}', "armadura": arm_real,
            "grave": dizer(min(reais)) + str(min(reais) // 12 - 1),
            "agudo": dizer(max(reais)) + str(max(reais) // 12 - 1),
            "intervalo": 'sexta maior abaixo'}


def ritmo(comps):
    """Formula, figuras, sincope e densidade — tudo derivado da duracao lida.

    A formula sai da soma MODAL dos compassos: anacruse e compasso final sao excecao
    legitima, entao a moda descreve a musica melhor que a media. `confianca` e a fracao
    de compassos que fecham nessa soma, e serve para nao afirmar ritmo em cima de leitura
    ruim (no modo contorno, por exemplo, pausa nao e lida).
    """
    if not comps:
        return None
    cont = collections.Counter(round(c["soma"], 4) for c in comps)
    modal, n_modal = cont.most_common(1)[0]
    figs = collections.Counter()
    for c in comps:
        for d, tipo in c["seq"]:
            if tipo == 'nota':
                figs[FIGURAS.get(round(d, 4), f'{round(d, 3)} tempos')] += 1
    sinc = fora = ataques = 0
    for c in comps:
        if abs(c["soma"] - modal) > 1e-6:
            continue          # compasso que nao fecha: a posicao dentro dele nao vale
        t = 0.0
        for d, tipo in c["seq"]:
            if tipo == 'nota':
                ataques += 1
                if abs(t - round(t)) > 1e-6:
                    fora += 1
                    # sincope = ataque fora do tempo que ATRAVESSA o tempo seguinte. Quem
                    # so preenche o contratempo e conta como fora do tempo, nao sincope.
                    if t + d > int(t) + 1 + 1e-6:
                        sinc += 1
            t += d
    denso = max(comps, key=lambda c: c["n_notas"])
    return {"formula": FORMULAS.get(modal, f'{modal} tempos de semínima'),
            "tempos": modal, "confianca": round(n_modal / len(comps), 2),
            "figuras": figs.most_common(5),
            "predominante": figs.most_common(1)[0][0] if figs else None,
            "sincopes": sinc, "frac_sincope": round(sinc / max(1, ataques), 3),
            "frac_fora_do_tempo": round(fora / max(1, ataques), 3),
            "densidade": round(sum(c["n_notas"] for c in comps) / len(comps), 1),
            "mais_denso": {"compasso": denso["num"], "notas": denso["n_notas"]}}


def respiros(comps, limite=12.0, pausa_min=1.0, nota_min=3.0):
    """Onde cabe respirar, e onde a frase passa do sopro.

    Respiro = pausa de um tempo para cima, ou nota de tres tempos para cima (da tempo de
    cortar o fim dela e pegar ar). Pausa de colcheia NAO conta: no meio de uma levada de
    semicolcheia ela e articulacao, nao folga — com meio tempo de limite, o The-chicken
    apareceu com 46 "respiros" em 28 compassos, o que nao descreve nada.

    Frase e o que vem entre dois respiros; acima de ~12 tempos corridos o ar acaba, e ai
    vale escolher onde roubar antes de precisar.
    """
    if not comps:
        return None
    frases, corrido, inicio = [], 0.0, comps[0]["num"]
    pontos = []
    for c in comps:
        for d, tipo in c["seq"]:
            folga = (tipo == 'pausa' and d >= pausa_min) or (tipo == 'nota' and d >= nota_min)
            if folga:
                if tipo == 'nota':
                    corrido += d
                pontos.append(c["num"])
                frases.append({"tempos": round(corrido, 2), "do": inicio, "ao": c["num"]})
                corrido, inicio = 0.0, c["num"]
            else:
                corrido += d
    if corrido > 0:
        frases.append({"tempos": round(corrido, 2), "do": inicio, "ao": comps[-1]["num"]})
    longas = sorted((f for f in frases if f["tempos"] > limite),
                    key=lambda f: -f["tempos"])
    return {"pontos": len(pontos), "frases": len(frases),
            "media": round(sum(f["tempos"] for f in frases) / max(1, len(frases)), 1),
            "longas": longas[:3], "limite": limite}


def motivos(seq, janela=4, minimo=2):
    """O mesmo desenho repetido, ainda que em outra altura.

    Compara INTERVALOS e nao notas: e o que faz "G A B G" e "C D E C" contarem como o
    mesmo motivo — que e como o ouvido escuta e como se estuda. `seq` e
    [(compasso, midi, nome)] na ordem de leitura.
    """
    ocor = {}
    for i in range(len(seq) - janela):
        iv = tuple(seq[i + k + 1][1] - seq[i + k][1] for k in range(janela))
        if all(v == 0 for v in iv) or max(abs(v) for v in iv) > 12:
            continue
        ocor.setdefault(iv, []).append(i)
    saida = []
    for iv, pos in ocor.items():
        # ocorrencias sobrepostas sao a MESMA passagem contada varias vezes
        limpo = []
        for p in pos:
            if not limpo or p - limpo[-1] >= janela:
                limpo.append(p)
        if len(limpo) < minimo:
            continue
        i0 = limpo[0]
        saida.append({"notas": [seq[i0 + k][2] for k in range(janela + 1)],
                      "vezes": len(limpo),
                      "compassos": sorted({seq[p][0] for p in limpo})[:8],
                      "transposto": len({seq[p][1] for p in limpo}) > 1})
    saida.sort(key=lambda m: (-m["vezes"], m["compassos"][0]))
    return saida[:3]


# Registro do sax alto, em nota ESCRITA: Bb3 (58) a F#6 (90) e o padrao do instrumento.
# Da chave de palma (86) para cima o dedilhado muda de mao; acima de 90 e altissimo.
ESCR_GRAVE, ESCR_AGUDO = 58, 90
PALMA, MESA = 86, 61


def registro(midis):
    """Quanto da musica cai em cada regiao do instrumento — o que muda o dedilhado."""
    return {"palma": sum(1 for m in midis if PALMA <= m <= ESCR_AGUDO),
            "altissimo": sum(1 for m in midis if m > ESCR_AGUDO),
            "mesa": sum(1 for m in midis if m <= MESA),
            "abaixo_do_sax": sum(1 for m in midis if m < ESCR_GRAVE)}


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


def analisar(dados, sistema="letras"):
    """Recebe bytes de PDF, devolve um dicionario de fatos medidos.

    Com `sistema="dore"`, os nomes de nota da saida vem em do-re-mi.
    """
    doc = pymupdf.open(stream=dados, filetype="pdf")
    notas, cifras, compassos, linhas_vistas = [], [], {}, []

    def caixa(ch):
        return compassos.setdefault(ch, {"notas": [], "pausas": []})

    for pg in doc:
        # uma coleta so, COM ritmo, reaproveitada por ler_notas: e o que da duracao e
        # pausa para a analise de ritmo e de respiro sem ler a pagina duas vezes
        col = A.coletar(pg, com_ritmo=True)
        textos, horiz, formas = col[1], col[2], col[4]
        sistemas = A.pautas(horiz, pg.rect.width, pg.rect.height)
        rot, _, pausas = A.ler_notas(pg, "letras", com_pausas=True, dados=col)
        for r in sorted(rot, key=lambda r: (r["sistema"], r["x"])):
            notas.append(dict(r, pagina=pg.number))
            caixa((pg.number, r["sistema"], r["compasso"]))["notas"].append(r)
        for p in pausas:
            caixa((pg.number, p["sistema"], p["compasso"]))["pausas"].append(p)
        # A cifra e situada pelo SISTEMA, nao pelo compasso. O compasso da cifra teria de
        # sair da barra mais proxima, e a barra que eu recalcularia aqui nao e a mesma que
        # o nucleo usa (haste longa entra como barra): a linha da partitura e um endereco
        # exato, o numero de compasso seria um palpite.
        for c in ler_cifras(pg, sistemas, textos, formas):
            c["linha"] = len(linhas_vistas) + c["sistema"]
            # posicao relativa na largura da pagina: e o que faz a folha de cifras mostrar
            # que um acorde durou meio sistema e o seguinte, dois compassos
            c["xr"] = round(c["x"] / pg.rect.width, 4)
            cifras.append(c)
        linhas_vistas.extend(range(len(sistemas)))
    doc.close()
    if not notas:
        return None

    midis = [r["midi"] for r in notas]
    arm = collections.Counter(r["armadura"] for r in notas).most_common(1)[0][0]
    tom, relativa, _ = detectar_tom(midis, arm)
    # tendo cifra, a harmonia manda no maior x menor; a melodia fica como desempate
    por = 'melodia'
    veredito = tom_pelas_cifras([c["cifra"] for c in cifras
                                 if not c["cifra"].startswith("N")], arm)
    if veredito and not tom.endswith(veredito):
        tom, relativa, por = relativa, tom, 'cifra'
    elif veredito:
        por = 'cifra'
    _ton, _modo = tom.rsplit(' ', 1)

    # ordem de leitura dos compassos -> numero global, que e como o musico conta
    ordem = sorted(compassos)
    num = {ch: i + 1 for i, ch in enumerate(ordem)}
    comps = []
    for ch in ordem:
        c = compassos[ch]
        # acorde: varias cabecas no mesmo x contam UMA vez, igual ao validador de ritmo
        vistos, itens = set(), []
        for r in sorted(c["notas"], key=lambda r: r["x"]):
            k = round(r["x"], 1)
            if r["graca"] or k in vistos:
                continue
            vistos.add(k)
            itens.append((r["x"], r["dur"], 'nota'))
        itens += [(p["x"], p["dur"], 'pausa') for p in c["pausas"]]
        itens.sort()
        comps.append({"num": num[ch], "pagina": ch[0] + 1, "sistema": ch[1] + 1,
                      "seq": [(d, t) for _, d, t in itens],
                      "soma": round(sum(d for _, d, _ in itens), 4),
                      "n_notas": sum(1 for _, _, t in itens if t == 'nota')})

    # compassos mais dificeis: extensao + saltos + alteracoes dentro do compasso
    dif = []
    for chave, cx in compassos.items():
        rs = cx["notas"]
        if len(rs) < 2:
            continue
        ms = [r["midi"] for r in rs]
        saltos = [abs(b - a) for a, b in zip(ms, ms[1:])]
        pontos = (max(ms) - min(ms)) * 0.25 + max(saltos) * 0.5 \
            + sum(1 for r in rs if r["alt"]) * 1.2 + len(rs) * 0.2 \
            + sum(1 for m in ms if m >= 84) * 1.5
        razoes = []
        if max(saltos) >= 9:
            razoes.append(f"salto de {max(saltos)} semitons")
        if any(m >= 84 for m in ms):
            razoes.append("agudo de chave de palma")
        if any(m <= 61 for m in ms):
            razoes.append("grave de mindinho")
        n_alt = sum(1 for r in rs if r["alt"])
        if n_alt >= 2:
            razoes.append(f"{n_alt} notas alteradas")
        if len(rs) >= 8:
            razoes.append(f"{len(rs)} notas no compasso")
        dif.append({"pagina": chave[0] + 1, "sistema": chave[1] + 1,
                    "compasso": num[chave], "notas": len(rs),
                    "pontos": round(pontos, 1),
                    "motivos": razoes or ["nada de especial"]})
    dif.sort(key=lambda d: -d["pontos"])

    freq = collections.Counter(r["nome"] for r in notas)
    seq_comp = [tuple(r["midi"] for r in cx["notas"]) for cx in compassos.values()]
    unicos = len(set(seq_comp))

    reais = [c for c in cifras if not c["cifra"].startswith("N")]
    cifras_unicas = list(dict.fromkeys(c["cifra"] for c in reais))
    escala_tom = escala_do_tom(_ton, arm)
    pcs_tom = [p for _, p in escala_tom]
    prog = [{"cifra": c["cifra"], "linha": c["linha"] + 1} for c in reais]
    seq_f = funcional(prog, _ton, _modo, arm) if prog else []

    rit = ritmo(comps)
    # respiro depende de PAUSA lida; onde o ritmo nao fecha (modo contorno, quialtera) a
    # posicao dentro do compasso nao vale, e um mapa de respiro errado atrapalha mais que ajuda
    resp = respiros(comps) if rit and rit["confianca"] >= 0.6 else None

    # cromatismo: nota que nao pertence ao tom. E o que o estudo de aproximacao persegue
    fora = collections.Counter(r["nome"] for r in notas
                               if _classe(r["nome"]) not in pcs_tom)
    seq_mot = [(num[(r["pagina"], r["sistema"], r["compasso"])], r["midi"], r["nome"])
               for r in notas if not r["ligada"] and not r["graca"]]

    saida = {
        "n_notas": len(notas),
        "tom": tom,
        "tom_relativo": relativa,
        "tom_por": por,
        "armadura": arm,
        "escala_do_tom": [n for n, _ in escala_tom],
        "grave": CLASSES[min(midis) % 12] + str(min(midis) // 12 - 1),
        "agudo": CLASSES[max(midis) % 12] + str(max(midis) // 12 - 1),
        "extensao": max(midis) - min(midis),
        "real": som_real(_ton, _modo, arm, midis),
        "registro": registro(midis),
        "frac_alteradas": round(sum(1 for r in notas if r["alt"]) / len(notas), 3),
        "fora_do_tom": fora.most_common(6),
        "mais_tocadas": freq.most_common(5),
        "cifras": cifras_unicas,
        "progressao": [c["cifra"] for c in reais[:24]],
        "escalas": [{"cifra": c, "escala": escala_da_cifra(c), "notas": soletrar(c),
                     "grau": grau_de_cifra(c, escala_tom)}
                    for c in cifras_unicas[:14]],
        "funcional": [{k: v for k, v in it.items() if k != "pc"} for it in seq_f[:32]],
        "cadencias": cadencias(seq_f, arm)[:8],
        "blues": e_blues(seq_f, _ton, arm) if seq_f else None,
        "campo": campo_harmonico(_ton, _modo, arm),
        "ritmo": rit,
        "respiro": resp,
        "motivos": motivos(seq_mot),
        "compassos": len(compassos),
        "compassos_distintos": unicos,
        "repeticao": round(1 - unicos / max(1, len(compassos)), 2),
        "dificeis": dif[:3],
        # grade da folha de cifras: uma LINHA por sistema da partitura, na ordem de
        # leitura, com as cifras daquele sistema na ordem de x
        # a melodia como texto, compasso por compasso: e o que a folha de leitura estampa.
        # Cabeca presa por ligadura fica de fora, igual ao que e escrito na pauta — ela nao
        # e um ataque novo, e repetir o nome atrapalharia a leitura.
        "leitura": [{"c": num[(r["pagina"], r["sistema"], r["compasso"])], "n": r["nome"]}
                    for r in notas if not r["ligada"] and not r["graca"]],
        "grade": [{"linha": i + 1,
                   "cifras": [{"cifra": c["cifra"], "xr": c["xr"], "x": round(c["x"], 2),
                               "grau": grau_de_cifra(c["cifra"], escala_tom)}
                              for c in sorted(cifras, key=lambda c: c["x"])
                              if c["linha"] == i]}
                  for i in range(len(linhas_vistas))],
    }
    return _traduzir(saida) if sistema == "dore" else saida


def _voz(cifra, base=48):
    """Cifra -> notas MIDI para tocar: baixo uma oitava abaixo e o acorde fechado acima.

    Fechado de proposito: acorde espalhado disputa a regiao do sax e embola. O baixo
    separado e o que faz a harmonia se sustentar sozinha embaixo da melodia.
    """
    pcs = [_classe(n) for n in soletrar(cifra) if '(' not in n]
    pcs = [p for p in pcs if p is not None]
    if not pcs:
        return []
    raiz = base + pcs[0] % 12
    return [raiz - 12] + [raiz + (p - pcs[0]) % 12 for p in pcs[:5]]


def _instante(pontos, x):
    """Interpola o tempo de um x na linha, pelos (x, t) das notas dela."""
    if not pontos:
        return None
    if x <= pontos[0][0]:
        return pontos[0][1]
    if x >= pontos[-1][0]:
        return pontos[-1][1]
    for (x0, t0), (x1, t1) in zip(pontos, pontos[1:]):
        if x0 <= x <= x1:
            fatia = 0.0 if x1 == x0 else (x - x0) / (x1 - x0)
            return t0 + fatia * (t1 - t0)
    return pontos[-1][1]


def acompanhamento(dados, info):
    """[{t, d, midi}] — a harmonia lida, no relogio da melodia, para tocar por baixo.

    A cifra nao tem tempo, tem posicao: o instante dela sai por INTERPOLACAO entre os x
    das notas da mesma linha, que ja passaram pelo relogio em `melodia`. Linha sem nota
    (intro em barra inclinada) nao entra — ali nao existe referencia de tempo nenhuma.

    A duracao de cada acorde vai ate o proximo: e assim que um acompanhamento se comporta,
    sustentando enquanto ninguem trocou de acorde.
    """
    grade = (info or {}).get("grade") or []
    if not grade:
        return []
    mel = A.melodia(dados)
    por_linha = {}
    for e in mel["notas"]:
        if "s" in e:
            por_linha.setdefault(e["s"], []).append((e["x"], e["t"]))
    for v in por_linha.values():
        v.sort()
    seq = []
    for g in grade:
        pontos = por_linha.get(g["linha"] - 1)
        for c in g["cifras"]:
            t = _instante(pontos, c["x"]) if pontos else None
            if t is not None:
                seq.append({"t": round(t, 4), "cifra": c["cifra"]})
    seq.sort(key=lambda a: a["t"])
    # repeticao imediata do mesmo acorde vira um so: nao ha o que reatacar
    limpo = []
    for a in seq:
        if limpo and limpo[-1]["cifra"] == a["cifra"] and a["t"] - limpo[-1]["t"] < 0.5:
            continue
        limpo.append(a)
    saida = []
    for i, a in enumerate(limpo):
        fim = limpo[i + 1]["t"] if i + 1 < len(limpo) else mel["total"]
        d = round(fim - a["t"], 4)
        midi = _voz(a["cifra"])
        if d > 0.05 and midi:
            saida.append({"t": a["t"], "d": d, "midi": midi, "cifra": a["cifra"]})
    return saida


def folha_de_notas(info, titulo=''):
    """PDF NOVO com a melodia escrita por extenso, compasso por compasso.

    Sem pauta, sem figura, sem duracao: so a ordem das notas. Serve para quem esta
    aprendendo a associar nome e dedilhado e ainda tropeca na leitura da pauta — e para
    conferir de cabeca, longe do instrumento. O nome sai no sistema que foi pedido na
    entrada, entao com "Do Re Mi" marcado a folha toda vem em do-re-mi.

    Devolve bytes de PDF, ou None se nao houver nota lida.
    """
    seq = (info or {}).get("leitura") or []
    if not seq:
        return None
    por_compasso = []
    for e in seq:
        if not por_compasso or por_compasso[-1][0] != e["c"]:
            por_compasso.append((e["c"], []))
        por_compasso[-1][1].append(e["n"])

    doc = pymupdf.open()
    LARG, ALT = 595.0, 842.0
    marg, h = 52.0, 23.0
    cinza, claro, preto = (0.42, 0.42, 0.42), (0.68, 0.68, 0.68), (0, 0, 0)
    pg, y = None, 0.0

    def nova_pagina(primeira):
        nonlocal pg, y
        pg = doc.new_page(width=LARG, height=ALT)
        if primeira:
            pg.insert_text((marg, 66), titulo or 'Notas da melodia', fontname='hebo',
                           fontsize=17)
            meta = [info["tom"]]
            if info.get("real"):
                meta.append('soa em ' + info["real"]["tom"])
            meta.append(f'{len(seq)} notas')
            pg.insert_text((marg, 84), '  ·  '.join(meta), fontname='helv', fontsize=9.5,
                           color=cinza)
            y = 116.0
        else:
            y = 72.0

    nova_pagina(True)
    for numero, nomes in por_compasso:
        # compasso comprido continua na linha de baixo, com o numero repetido em claro
        pedacos, atual = [], []
        for nm in nomes:
            atual.append(nm)
            if len(atual) == 12:
                pedacos.append(atual)
                atual = []
        if atual:
            pedacos.append(atual)
        for i, pedaco in enumerate(pedacos):
            if y + h > ALT - 52:
                nova_pagina(False)
            pg.insert_text((marg - 26, y), str(numero), fontname='helv', fontsize=8,
                           color=claro if i else cinza)
            x = marg
            for nm in pedaco:
                pg.insert_text((x, y), nm, fontname='hebo', fontsize=12, color=preto)
                x += max(30.0, pymupdf.get_text_length(nm, fontname='hebo', fontsize=12) + 12)
            y += h
    saida = doc.tobytes()
    doc.close()
    return saida


def folha_de_cifras(info, titulo=''):
    """PDF NOVO so com a harmonia: uma faixa por LINHA da partitura, com o grau embaixo.

    Nao e a partitura recortada — e uma folha gerada de zero, para quando o que se quer no
    atril e a sequencia de acordes e nao a melodia. O agrupamento segue as linhas do
    original: a 3a faixa daqui e a 3a linha de la, o que faz procurar um trecho ser
    imediato. O grau embaixo da cifra e o que permite tocar a mesma musica em outro tom.

    Devolve bytes de PDF, ou None se a partitura nao trouxe cifra.
    """
    grade = [g for g in ((info or {}).get("grade") or []) if g["cifras"]]
    if not grade or not info.get("cifras"):
        return None
    doc = pymupdf.open()
    LARG, ALT = 595.0, 842.0
    marg, h = 46.0, 62.0
    cinza, claro, preto = (0.45, 0.45, 0.45), (0.72, 0.72, 0.72), (0, 0, 0)
    pg, y = None, 0.0

    def nova_pagina(primeira):
        nonlocal pg, y
        pg = doc.new_page(width=LARG, height=ALT)
        if primeira:
            pg.insert_text((marg, 66), titulo or 'Folha de cifras', fontname='hebo',
                           fontsize=17)
            meta = [info["tom"]]
            if info.get("real"):
                meta.append('soa em ' + info["real"]["tom"])
            if info.get("ritmo"):
                meta.append(info["ritmo"]["formula"])
            meta.append(f'{len(info["cifras"])} acordes')
            pg.insert_text((marg, 84), '  ·  '.join(meta), fontname='helv',
                           fontsize=9.5, color=cinza)
            y = 124.0
        else:
            y = 76.0

    nova_pagina(True)
    util = LARG - 2 * marg
    for g in grade:
        if y + h > ALT - 46:
            nova_pagina(False)
        # Cada cifra fica na MESMA posicao relativa que tinha na pauta: assim o espaco entre
        # duas cifras conta quanto tempo o acorde durou, que e a informacao que uma grade de
        # celulas iguais joga fora. O empurrao usa a largura MEDIDA do texto, nao um minimo
        # fixo: com 44 pt fixos, "B7(b9)" e "Em" sairam colados um no outro.
        tam = 15.0 if len(g["cifras"]) <= 6 else 11.0
        largo = [pymupdf.get_text_length(c["cifra"], fontname='hebo', fontsize=tam) + 12
                 for c in g["cifras"]]
        sobra = util - sum(largo)
        xs = []
        for i, c in enumerate(g["cifras"]):
            x = marg + max(0.0, min(1.0, (c["xr"] - 0.09) / 0.84)) * max(0.0, sobra)
            x += sum(largo[:i])
            if xs and x < xs[-1] + largo[i - 1]:
                x = xs[-1] + largo[i - 1]
            xs.append(x)
        pg.insert_text((marg - 14, y - 2), str(g["linha"]), fontname='helv', fontsize=7.5,
                       color=claro)
        for x, c in zip(xs, g["cifras"]):
            pg.draw_line((x - 6, y - 20), (x - 6, y + 8), color=claro, width=0.7)
            pg.insert_text((x, y), c["cifra"], fontname='hebo', fontsize=tam, color=preto)
            grau = c.get("grau") or ""
            if grau:
                pg.insert_text((x, y + 16), grau, fontname='helv', fontsize=8, color=cinza)
        pg.draw_line((LARG - marg, y - 20), (LARG - marg, y + 8), color=claro, width=0.7)
        y += h
    saida = doc.tobytes()
    doc.close()
    return saida


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    r = analisar(open(sys.argv[1], "rb").read())
    if not r:
        print("nenhuma nota legivel")
        return 1
    if "--notas" in sys.argv:
        alvo = os.path.splitext(sys.argv[1])[0] + "_leitura.pdf"
        pdf = folha_de_notas(r, os.path.basename(os.path.splitext(sys.argv[1])[0]))
        if not pdf:
            print("nenhuma nota lida")
            return 1
        open(alvo, "wb").write(pdf)
        print(alvo)
        return 0
    if "--cifras" in sys.argv:
        alvo = os.path.splitext(sys.argv[1])[0] + "_cifras.pdf"
        pdf = folha_de_cifras(r, os.path.basename(os.path.splitext(sys.argv[1])[0]))
        if not pdf:
            print("essa partitura nao trouxe cifra")
            return 1
        open(alvo, "wb").write(pdf)
        print(alvo)
        return 0
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
