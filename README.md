# anotar-partitura

Escreve o **nome de cada nota embaixo da pauta**, direto no PDF da partitura. O PDF de
saída é o original + uma camada de texto: nada é re-desenhado, o layout do arranjador
fica intacto.

**➜ [Usar no navegador](https://manuelstv.github.io/anotar-partitura/)** — arraste o PDF,
baixe o anotado. Roda 100% no seu navegador (Pyodide + PyMuPDF em WebAssembly); o arquivo
não é enviado para servidor nenhum.

## Como funciona

Não é OCR nem rede neural — é **aritmética sobre as coordenadas do PDF**. Partitura gerada
por computador guarda cada cabeça de nota como um *caractere* de uma fonte musical, e as
linhas da pauta como vetor. Então:

1. lê as linhas horizontais → acha pautas por **periodicidade** (5 linhas de passo igual,
   tolerando beam/colchete intercalado);
2. lê os glifos da fonte musical → clave, armadura, acidentes, cabeças de nota;
3. altura = quantos meio-espaços a cabeça está acima da linha de cima da pauta;
4. aplica armadura, acidente explícito e a regra de que o acidente vale até a barra;
5. estampa o nome embaixo da pauta, abaixo de hastes/ligaduras, com 2ª fileira quando
   os nomes colidem.

A posição vertical medida cai a menos de **0,05 meio-espaço** do valor exato — a leitura
não "chuta". Todo limiar de geometria é o valor validado em A4 multiplicado pela escala da
página, porque o mesmo A4 aparece gravado em escalas diferentes (já vi 595×842 e
2976×4209 na mesma pasta).

## Cobertura

| Origem do PDF | Fontes | Status |
|---|---|---|
| MuseScore / Dorico | Leland, Bravura, Petaluma… | ✅ SMuFL |
| Sibelius | Opus | ✅ layout Sonata |
| Finale | Maestro | ✅ layout Sonata |
| PDF escaneado (imagem) | — | ❌ precisa de OMR (Audiveris/oemer) |

Clave de sol, fá e dó. Só a de sol foi testada de fato (é o caso de sax).
Pauta de **ritmo** (1 linha) não recebe nome — não há altura para ler.

## Precisão medida

Validado contra partituras que **já traziam** os nomes impressos, casando nota↔nome por
coluna x:

| Conjunto | Programa | Resultado |
|---|---|---|
| Negra ron y velas (sax alto) | MuseScore | 154/154 = **100%** |
| The-chicken (alto + tenor) | Sibelius | 98/98 = **100%** |
| Acervo Online Sax Academy — 182 PDFs "With Note Names" | Sibelius | ver `RESULTADOS.md` |

No The-chicken, 2 notas divergiram dos nomes impressos no próprio PDF — a conferência
(posição na pauta + a transposição alto→tenor da mesma peça) mostrou que os nomes **do
PDF** estavam errados, não a leitura.

## Linha de comando

```bash
uv run anotar_partitura.py "partitura.pdf"                   # C D E F G A B
uv run anotar_partitura.py "partitura.pdf" --sistema dore    # Do Re Mi Fa Sol La Si
uv run anotar_partitura.py "partitura.pdf" --limpar          # cobre nomes antigos
```

| flag | o que faz |
|---|---|
| `-o` | PDF de saída (default: `<nome>_notas.pdf`) |
| `--sistema` | `letras` (default) ou `dore` |
| `--limpar` | cobre nomes de nota que já estavam na partitura |
| `--cor` | R,G,B de 0 a 1 (default `0,0,0.75`, azul escuro) |

`--limpar` é heurístico. Duas travas evitam apagar cifra de acorde: só limpa se houver
nome para ≥50% das notas, e só apaga a família dominante (se a anotação está em Do-Re-Mi,
um "F" solto é cifra e fica). Ainda assim, confira o resultado.

## Arquivos

- `anotar_partitura.py` — a ferramenta (mesmo arquivo usado pelo site e pela CLI)
- `index.html` — a interface web (carrega o `.py` acima e roda no Pyodide)

Técnica de extração vetorial inspirada em
[vitorfornaro/awesome-music-sheets](https://github.com/vitorfornaro/awesome-music-sheets)
(`tools/vector_extract.py`).
