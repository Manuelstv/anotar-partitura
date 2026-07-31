#!/usr/bin/env python3
"""Leitura de partitura a partir de IMAGEM (print de celular, JPG/PNG, PDF escaneado).

O nucleo nao precisa de vetor: precisa de `horiz` (as linhas da pauta) e `caminhos`
(manchas com caixa e "tem buraco"). Este modulo produz esses dois a partir de pixels e
devolve exatamente a tupla que `coletar()` devolveria — do saguao em diante,
`glifos_de_contorno` e `ler_notas` seguem sem saber que a origem foi uma imagem.

Duas coisas fazem isso funcionar:

1. TUDO e medido em ESPACOS DE PAUTA, nunca em pixels absolutos. O espaco sai da propria
   deteccao das linhas, e e o que torna o modulo indiferente ao zoom do print. Abaixo de
   ~8 px por espaco a leitura degrada rapido (medido: 6 px -> 44% das cabecas).
2. A cabeca de nota nao e achada por "parece uma elipse", e sim por tres perguntas de
   NOTACAO: com que classe de glifo ela se parece mais (banco de templates), ela mora em
   linha ou espaco, e ela tem haste encostada. So a primeira e aparencia.

Medido em 601 notas de 4 arquivos (treino do banco em 2 obras diferentes):
96,7% das cabecas, 100% do grau diatonico, 1,7% de falso positivo.

Detalhe do enquadramento: a imagem entra num PDF de uma pagina em escala 1:1
(1 pixel = 1 ponto), entao as coordenadas que este modulo devolve ja servem para o
`escrever()` estampar em cima, sem conversao.
"""
import base64
import json
import os

import numpy as np

try:
    import cv2
except ImportError:                  # sem opencv o modo imagem nao existe; PDF segue
    cv2 = None

LADO = 24                # patch normalizado do banco, em pixels
JANELA = 2.4             # lado da janela recortada, em espacos de pauta
CABECAS = ("preta", "minima", "semibreve")
MARGEM = 0.12            # folga exigida da melhor classe de cabeca sobre a melhor "nao"
LIMIAR_CAND = 0.34       # correlacao minima para virar candidato
ALT_HASTE = 2.2          # altura minima de uma haste, em espacos
ALT_HASTE_MIN = 1.8      # idem, no teste de haste (mais frouxo)
LARG_HASTE = 0.80        # largura maxima de uma haste no teste de haste, em espacos
ALINHA_MAX = 0.18        # desvio maximo do meio-espaco, em espacos
ESP_MINIMO = 5.0         # abaixo disso em pixels nem vale tentar
AREA_MIOLO = 0.85        # area maxima de buraco a tapar, em espacos^2

_BANCO = None            # (matriz float32 normalizada, lista de rotulos)


class SemOpenCV(RuntimeError):
    pass


class ImagemIlegivel(RuntimeError):
    pass


# ------------------------------------------------------------------- banco
def carregar_banco(caminho=None, texto=None):
    """Le o banco de templates gerado por `_exploracao/gerar_banco.py`.

    No site o JSON chega como texto (fetch); na CLI, como arquivo ao lado do modulo.
    """
    global _BANCO
    if texto is None:
        caminho = caminho or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                          "templates_bitmap.json")
        with open(caminho) as fp:
            texto = fp.read()
    d = json.loads(texto)
    M = np.frombuffer(base64.b64decode(d["float16_b64"]), dtype=np.float16)
    M = M.reshape(d["forma"]).astype(np.float32)
    _BANCO = (M, list(d["rotulos"]))
    return _BANCO


def banco():
    return _BANCO if _BANCO is not None else carregar_banco()


# ------------------------------------------------------- linhas e limpeza
def binarizar(img):
    """Cinza -> tinta = 1. Otsu, que se ajusta sozinho ao contraste do print."""
    g = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    _, b = cv2.threshold(g, 0, 1, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    return b.astype(np.uint8)


def achar_horiz(bin_, frac_min=0.18, folga=4):
    """Fileiras densas -> (y, x0, x1) do maior run de tinta, tolerando buracos.

    Devolve UM segmento por fileira, o mais longo — e nao os pedacos. `pautas()` mede a
    UNIAO dos segmentos de cada nivel, e um punhado de tracos curtos empilhados viraria
    uma "linha longa" fantasma, deslocando a pauta uma linha inteira.
    """
    H, W = bin_.shape
    soma = bin_.sum(axis=1)
    fileiras = np.flatnonzero(soma >= frac_min * W)
    out = []
    for y in fileiras:
        xs = np.flatnonzero(bin_[y])
        if len(xs) < 2:
            continue
        quebras = np.flatnonzero(np.diff(xs) > folga)
        ini = np.concatenate(([0], quebras + 1))
        fim = np.concatenate((quebras, [len(xs) - 1]))
        k = int(np.argmax(xs[fim] - xs[ini]))
        x0, x1 = int(xs[ini[k]]), int(xs[fim[k]])
        if x1 - x0 >= 0.15 * W:
            out.append((float(y), float(x0), float(x1)))
    espessuras, atual = [], None
    for y in fileiras:                      # espessura = run vertical de fileiras densas
        if atual is not None and y - atual[-1] <= 1:
            atual.append(y)
        else:
            if atual:
                espessuras.append(len(atual))
            atual = [y]
    if atual:
        espessuras.append(len(atual))
    return out, max(1, int(np.median(espessuras)) if espessuras else 1)


def limpar(bin_, ys_linha, esp_linha):
    """Apaga a linha de pauta preservando o que a atravessa.

    Um pixel de linha e apagado so se NAO pertence a nenhum traco vertical mais alto que
    ~2,5x a espessura da linha — e isso que salva cabeca, haste, barra e acidente.

    NAO remover haste. O sustenido tambem e feito de dois tracos verticais compridos e
    estreitos: apagar haste por geometria apaga a armadura junto, e todo nome sai sem
    alteracao (medido: 98,6% -> 22,8%). Como a cabeca vem de correlacao e nao de
    componente conexo, nao ha motivo para remover haste.
    """
    alto = max(3, int(round(2.5 * esp_linha)) | 1)
    vert_longo = cv2.morphologyEx(bin_, cv2.MORPH_OPEN,
                                  cv2.getStructuringElement(cv2.MORPH_RECT, (1, alto)))
    out = bin_.copy()
    mascara = np.zeros(bin_.shape[0], dtype=bool)
    mascara[np.clip(ys_linha, 0, bin_.shape[0] - 1)] = True
    out[mascara[:, None] & (bin_ == 1) & (vert_longo == 0)] = 0
    return cv2.morphologyEx(out, cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_RECT,
                                                      (1, esp_linha + 2)))


def preencher_buracos(b, area_max):
    """Tapa SO buraco pequeno — o miolo de uma minima.

    Tapar todo buraco fechado inunda tambem a area cercada por haste + beam + a cabeca
    vizinha, que e enorme: a mancha vira um bloco solido e a correlacao com a elipse
    desaba.
    """
    n, lab, stats, _ = cv2.connectedComponentsWithStats(1 - b, connectivity=4)
    H, W = b.shape
    tapar = np.zeros(n, bool)
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if not (x == 0 or y == 0 or x + w >= W or y + h >= H) and area <= area_max:
            tapar[i] = True
    return (b | tapar[lab]).astype(np.uint8)


# ----------------------------------------------------------------- deteccao
def _elipse(larg, esp, graus=-20.0):
    w = max(3, int(round(larg * esp)) | 1)
    h = max(3, int(round(1.06 * esp)) | 1)
    lado = int(max(w, h) * 1.6) | 1
    t = np.zeros((lado, lado), np.uint8)
    cv2.ellipse(t, (lado // 2, lado // 2), (w // 2, h // 2), graus, 0, 360, 1, -1)
    return t


def recortar(limpo, cx, cy, esp, lado=LADO, janela=JANELA):
    """Janela em unidades de ESPACO -> vetor de media zero e norma 1 (para correlacao)."""
    r = janela * esp / 2.0
    x0, x1 = int(round(cx - r)), int(round(cx + r))
    y0, y1 = int(round(cy - r)), int(round(cy + r))
    H, W = limpo.shape
    if x0 < 0 or y0 < 0 or x1 > W or y1 > H or x1 - x0 < 3 or y1 - y0 < 3:
        return None
    p = cv2.resize(limpo[y0:y1, x0:x1].astype(np.float32), (lado, lado),
                   interpolation=cv2.INTER_AREA)
    p -= p.mean()
    n = np.linalg.norm(p)
    return None if n < 1e-6 else (p / n).ravel()


def candidatos(cena):
    """Picos de correlacao com elipse de cabeca comum E de semibreve (mais larga).

    Dois geradores porque a semibreve tem ~1,75 espaco de largura contra 1,30 da cabeca
    comum: um template so nao acha as duas.
    """
    esp = cena["esp"]
    cheio = preencher_buracos(cena["limpo"], AREA_MIOLO * esp * esp)
    achados = []
    for larg in (1.30, 1.75):
        t = _elipse(larg, esp)
        resp = cv2.matchTemplate(cheio.astype(np.float32), t.astype(np.float32),
                                 cv2.TM_CCOEFF_NORMED)
        jan = max(3, int(round(0.9 * esp)) | 1)
        pico = cv2.dilate(resp, cv2.getStructuringElement(cv2.MORPH_RECT, (jan, jan)))
        ys, xs = np.nonzero((resp >= LIMIAR_CAND) & (resp >= pico - 1e-6))
        off = t.shape[0] // 2
        achados += [(float(x + off), float(y + off), float(resp[y, x]))
                    for y, x in zip(ys, xs)]
    achados.sort(key=lambda a: -a[2])
    fim = []
    for cx, cy, sc in achados:
        if any(abs(cx - a) < 0.7 * esp and abs(cy - b) < 0.7 * esp for a, b, _ in fim):
            continue
        fim.append((cx, cy, sc))
    return fim


def verticais(bin_, esp, larg_max=0.35, alt_min=None):
    """Tracos verticais: hastes e barras de compasso.

    O corte de altura em 2,2 espacos importa: com 1,2 espaco havia 507 verticais numa
    pagina de 156 notas e exigir haste nao filtrava nada.

    Sao geradas DUAS listas com esta funcao, de proposito (ver `coletar_da_imagem`):
    uma estreita, que vai para `ler_notas` decidir o que e barra de compasso, e uma
    frouxa, so para o teste de haste. Frouxo demais na primeira mexeria na regra do
    acidente que vale ate a barra; estreito demais na segunda descarta nota boa.
    """
    alt_min = ALT_HASTE if alt_min is None else alt_min
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(3, int(1.2 * esp) | 1)))
    v = cv2.morphologyEx(bin_, cv2.MORPH_OPEN, k)
    n, _, stats, _ = cv2.connectedComponentsWithStats(v, connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, _ = stats[i]
        if w <= max(2, larg_max * esp) and h >= alt_min * esp:
            out.append({"x": float(x + w / 2), "y0": float(y),
                        "y1": float(y + h), "h": float(h)})
    return out


def tem_haste(cx, cy, esp, vert):
    """Uma vertical com a PONTA em cima do centro da cabeca.

    Exigir que encoste (e nao apenas que exista por perto) e a mesma regra que o modo
    vetor usa: sem isso a haste da nota vizinha entra como candidata.
    """
    for v in vert:
        if abs(v["x"] - cx) > 0.72 * esp:
            continue
        if (v["y0"] - 0.55 * esp <= cy <= v["y0"] + 0.9 * esp
                or v["y1"] - 0.9 * esp <= cy <= v["y1"] + 0.55 * esp):
            return True
    return False


def largura_medida(cheio, cx, cy, esp, teto=2.6):
    """Extensao horizontal da mancha em volta do centro, em espacos de pauta.

    Serve para separar SEMIBREVE (~1,75 espaco) de minima (~1,30). Nao dava para deixar
    isso a cargo do banco: o acervo de treino tem UMA semibreve, e uma amostra nao treina
    classe nenhuma. Largura e geometria — nao precisa de exemplo para funcionar.

    A janela vertical cobre a cabeca INTEIRA (+-0,5 espaco), nao a linha do centro: no
    meio de uma semibreve ha o miolo VAZADO, e medir ali dava largura ZERO — a nota deixava
    de ser reconhecida como semibreve, caia na regra da haste (que ela nao tem) e era
    descartada. Eram 7 das 17 perdas.

    Se a mancha estoura o teto ela esta grudada em beam ou na cabeca vizinha; devolve o
    teto, e quem chama trata como "nao sei", nunca como semibreve.
    """
    H, W = cheio.shape
    y0, y1 = max(0, int(cy - 0.5 * esp)), min(H, int(cy + 0.5 * esp) + 1)
    if y0 >= y1:
        return 0.0
    faixa = cheio[y0:y1].any(axis=0)
    lim = int(teto * esp / 2)
    ini = int(round(cx))
    if not (0 <= ini < W) or not faixa[ini]:
        return 0.0
    e = ini
    while e > max(0, ini - lim) and faixa[e - 1]:
        e -= 1
    d = ini
    while d < min(W - 1, ini + lim) and faixa[d + 1]:
        d += 1
    return (d - e + 1) / esp


def cabecas(cena, vert_haste):
    """Candidato -> classe pelo banco -> filtro de notacao -> cabeca.

    O banco diz O QUE a mancha e; a notacao diz se ela PODE estar ali. Um sem o outro nao
    serve: banco sozinho da 61% de falso positivo, notacao sozinha nao distingue
    semibreve de letra "o".
    """
    M, rotulos = banco()
    nao_cab = np.array([i for i, r in enumerate(rotulos) if r not in CABECAS])
    esp = cena["esp"]
    cheio = preencher_buracos(cena["limpo"], AREA_MIOLO * esp * esp)
    out = []
    for cx, cy, _ in candidatos(cena):
        patch = recortar(cena["limpo"], cx, cy, esp)
        if patch is None:
            continue
        sim = M @ patch
        j = int(sim.argmax())
        classe = rotulos[j]
        if classe not in CABECAS:
            continue
        # A largura entra ANTES da margem: uma mancha larga e vazada e semibreve por
        # geometria, e o banco (que viu UMA no treino) as vezes chuta "texto" nela. Deixar
        # a margem decidir primeiro custava 3 notas.
        larg = largura_medida(cheio, cx, cy, esp)
        semibreve = 1.55 <= larg < 2.55 and classe != "preta"
        if not semibreve and len(nao_cab) and sim[j] - sim[nao_cab].max() < MARGEM:
            continue
        # mora em linha ou em espaco: o centro cai num multiplo de meio espaco
        s = min(cena["sistemas"], key=lambda s: abs((s[0] + s[-1]) / 2 - cy))
        e = (s[-1] - s[0]) / 4.0
        k = (cy - s[0]) / (e / 2.0)
        if abs(k - round(k)) * 0.5 > ALINHA_MAX:
            continue
        # SEMIBREVE nao tem haste nenhuma, e quem decide isso e a largura, nao o banco.
        # A letra "o" de um nome de nota impresso mede ~0,8 espaco, entao nao se disfarca
        # de semibreve; e a mancha grudada devolve o teto e cai no ramo que exige haste.
        if not semibreve and not tem_haste(cx, cy, esp, vert_haste):
            continue
        if semibreve:
            classe = "semibreve"
        # A caixa sai com a largura NOMINAL de cabeca (1,30 espaco) mesmo para semibreve,
        # que mede ~1,75 de verdade. Motivo: `glifos_de_contorno` filtra por
        # CABECA_W = (1,05, 1,60) e descartava toda semibreve logo depois de ela passar por
        # aqui — 14 notas de um arquivo so, e o diagnostico dizia que estavam passando.
        # A largura real ja fez o trabalho dela (decidir que era semibreve) acima.
        w = 1.30 * esp
        out.append({"x0": cx - w / 2, "x1": cx + w / 2,
                    "y0": cy - 0.53 * esp, "y1": cy + 0.53 * esp,
                    "w": w, "h": 1.06 * esp, "classe": classe,
                    # a figura vem da CLASSE, nao do pixel do meio
                    "curvas": 1 if classe == "preta" else 14})
    return out


ACC_W = (0.50, 1.20)     # faixa de acidente em `glifos_de_contorno`, replicada aqui
ACC_H = (2.20, 3.10)


def blobs(limpo, esp):
    """Manchas que NAO tem tamanho de cabeca: clave, acidente, ponto.

    Deixar o blob bruto virar cabeca dentro de `glifos_de_contorno` abre uma segunda
    porta de entrada, sem nenhum dos filtros do detector — era dali que vinha o falso
    positivo que nao reagia a nada.

    E quem tem tamanho de ACIDENTE tambem passa pelo banco. A FORMULA DE COMPASSO e o
    motivo: os dois digitos do "4/4", empilhados, formam uma mancha de ~1,0 x 2,7 espacos,
    que e exatamente a assinatura de um sustenido. Ela caia antes da primeira nota, virava
    armadura fantasma e o sistema inteiro saia com F# no lugar de F — 9 nomes errados num
    arquivo. Aqui o banco desempata, porque para ele digito e `texto`, nao `acc`.
    """
    cnts, hier = cv2.findContours(limpo, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is None:
        return []
    hier = hier[0]
    out = []
    for i, c in enumerate(cnts):
        if hier[i][3] != -1:
            continue
        x, y, w, h = cv2.boundingRect(c)
        if w * h < 4:
            continue
        if 1.05 <= w / esp <= 1.60 and 0.80 <= h / esp <= 1.35:
            continue                        # tamanho de cabeca: so o detector produz
        out.append({"x0": float(x), "x1": float(x + w), "y0": float(y),
                    "y1": float(y + h), "w": float(w), "h": float(h),
                    "curvas": 14 if hier[i][2] != -1 else 1})
    return out


def _tem_vertical_longa(limpo, c, fracao=0.94):
    """A mancha tem alguma COLUNA de tinta cobrindo `fracao` da propria altura?

    E o que separa acidente de PAUSA DE SEMINIMA. As duas medem ~1,0 x 2,9 espacos e
    `glifos_de_contorno` nao tem como distingui-las pela caixa — a pausa caia antes da
    primeira nota e virava armadura fantasma, com o sistema inteiro saindo F# no lugar de
    F. Mas sustenido e bequadro tem hastes verticais compridas e a pausa e um zigzag
    diagonal: nenhuma coluna dela atravessa a mancha de cima a baixo.

    Medido no acervo (fracao da altura coberta pela maior coluna de tinta):
    acidente real 0,79-1,00 (mediana 0,96); pausa real 0,35-0,93 (mediana 0,86 no pior
    arquivo). O corte em 0,94 mata toda pausa e custa uns poucos acidentes de imagem
    grande — na conta final o nome subiu de 97,4% para 98,1%.
    """
    x0, x1 = int(c["x0"]), int(min(limpo.shape[1], c["x1"]))
    y0, y1 = int(c["y0"]), int(min(limpo.shape[0], c["y1"]))
    if x1 - x0 < 2 or y1 - y0 < 3:
        return False
    rec = limpo[y0:y1, x0:x1]
    alvo = fracao * rec.shape[0]
    # maior sequencia contigua de tinta em cada coluna
    for col in rec.T:
        melhor = atual = 0
        for v in col:
            atual = atual + 1 if v else 0
            melhor = max(melhor, atual)
        if melhor >= alvo:
            return True
    return False


def tirar_pausas(caminhos, limpo, esp):
    """Descarta manchas com tamanho de acidente que nao tenham haste vertical."""
    return [c for c in caminhos
            if not (ACC_W[0] <= c["w"] / esp <= ACC_W[1]
                    and ACC_H[0] * 0.8 <= c["h"] / esp <= ACC_H[1]
                    and not _tem_vertical_longa(limpo, c))]


def tirar_formula(caminhos, sistemas, esp):
    """Descarta os digitos da FORMULA DE COMPASSO, que se disfarcam de acidente.

    Cada digito do "4/4" mede ~1,0 x 2,3 espacos, ou seja, cai na faixa de acidente de
    `glifos_de_contorno`; ficando antes da primeira nota, virava armadura fantasma e o
    sistema saia todo com F# no lugar de F. Foram 9 nomes errados num arquivo so.

    O que separa um do outro nao e o tamanho, e a ESTRUTURA: a formula e sempre um PAR
    alinhado em x, um digito na metade de cima da pauta e outro na de baixo. Sustenido de
    armadura vem sozinho na altura da nota que ele altera. (Mesma familia de solucao do
    ritornello, que se separa do ponto de aumento pelo par vertical.)

    Tentei antes deixar o BANCO desempatar isso e foi pior: a classe `acc` tem 6 templates
    de 2 obras e passou a rejeitar acidente legitimo — o nome caiu de 97,4% para 87,2%.
    """
    suspeitos = [c for c in caminhos
                 if ACC_W[0] <= c["w"] / esp <= ACC_W[1]
                 and ACC_H[0] * 0.85 <= c["h"] / esp <= ACC_H[1]]
    fora = set()
    for a in suspeitos:
        for b in suspeitos:
            if a is b or id(a) in fora:
                continue
            cxa, cxb = (a["x0"] + a["x1"]) / 2, (b["x0"] + b["x1"]) / 2
            if abs(cxa - cxb) > 0.35 * esp:
                continue
            cya, cyb = (a["y0"] + a["y1"]) / 2, (b["y0"] + b["y1"]) / 2
            if cya >= cyb:
                continue                              # conta o par uma vez so
            s = min(sistemas, key=lambda s: abs((s[0] + s[-1]) / 2 - cya))
            meio = (s[0] + s[-1]) / 2
            # um de cada lado do meio da pauta, e os dois dentro dela
            if (cya < meio < cyb and s[0] - 0.5 * esp < cya
                    and cyb < s[-1] + 0.5 * esp):
                fora.add(id(a))
                fora.add(id(b))
    return [c for c in caminhos if id(c) not in fora]


# -------------------------------------------------------------------- cena
def preparar(img, pautas=None):
    """Imagem -> {bin, limpo, sistemas, esp, horiz, W, H} ou None se nao houver pauta."""
    if cv2 is None:
        raise SemOpenCV("modo imagem exige opencv-python")
    if pautas is None:
        from anotar_partitura import pautas as pautas
    bin_ = binarizar(img)
    H, W = bin_.shape
    horiz, esp_linha = achar_horiz(bin_)
    sistemas = pautas(horiz, W, H)
    if not sistemas:
        return None
    esp = float(np.median([(s[-1] - s[0]) / 4.0 for s in sistemas]))
    if esp < ESP_MINIMO:
        return None
    ys = np.array(sorted({int(round(y)) for y, _, _ in horiz}))
    return {"bin": bin_, "limpo": limpar(bin_, ys, esp_linha), "sistemas": sistemas,
            "esp": esp, "esp_linha": esp_linha, "horiz": horiz, "W": W, "H": H}


def coletar_da_imagem(img, com_ritmo=False):
    """Mesma tupla de `coletar()`, produzida a partir de pixels.

    `glifos` volta vazio de proposito: e o que faz `ler_notas` cair no modo contorno, que
    ja sabe ler cabeca, clave e acidente por geometria em espacos de pauta. `textos` volta
    vazio porque imagem nao tem span de texto — e por isso a analise musical nao existe
    neste modo. `beams` volta vazio: o ritmo ainda nao e lido em imagem.
    """
    cena = preparar(img)
    if cena is None:
        raise ImagemIlegivel("nenhuma pauta encontrada na imagem")
    esp = cena["esp"]
    # estreita: e o que `ler_notas` usa para achar barra de compasso
    vert = verticais(cena["bin"], esp)
    # frouxa: so para o teste de haste. A haste sai gorda quando encosta em beam ou na
    # haste vizinha — medi 7 px (0,72 espaco) numa pagina do The-chicken, contra o limite
    # de 3,4 px. Eram 4 notas perdidas com a haste ali, encostando, visivel.
    vert_haste = verticais(cena["bin"], esp, larg_max=LARG_HASTE, alt_min=ALT_HASTE_MIN)
    outros = tirar_pausas(blobs(cena["limpo"], esp), cena["limpo"], esp)
    caminhos = cabecas(cena, vert_haste) + tirar_formula(outros, cena["sistemas"], esp)
    formas = [{"x": (c["x0"] + c["x1"]) / 2, "y": (c["y0"] + c["y1"]) / 2,
               "x0": c["x0"], "x1": c["x1"], "y0": c["y0"], "y1": c["y1"]}
              for c in caminhos]
    if com_ritmo:
        return [], [], cena["horiz"], vert, formas, caminhos, []
    return [], [], cena["horiz"], vert, formas, caminhos


def imagem_de_pixmap(pix):
    """Pixmap do PyMuPDF -> array RGB, sem passar por arquivo."""
    a = np.frombuffer(pix.samples, dtype=np.uint8)
    a = a.reshape(pix.height, pix.width, pix.n)
    return a[:, :, :3].copy() if pix.n >= 3 else cv2.cvtColor(a[:, :, 0],
                                                              cv2.COLOR_GRAY2RGB)


def decodificar(dados):
    """Bytes de imagem -> array cinza, direto, sem intermediario.

    Ler os pixels ORIGINAIS importa: passar a imagem por um PDF e rasterizar de volta
    reamostra o desenho, e a linha de pauta tem 1 pixel de espessura — ela borra, o Otsu
    perde a fileira densa e nenhuma pauta e encontrada. O PDF serve para ESTAMPAR, nao
    para ler.
    """
    if cv2 is None:
        raise SemOpenCV("modo imagem exige opencv-python")
    a = cv2.imdecode(np.frombuffer(dados, np.uint8), cv2.IMREAD_GRAYSCALE)
    if a is None:
        raise ImagemIlegivel("nao consegui decodificar a imagem")
    return a
