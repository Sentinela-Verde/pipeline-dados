# Datação da obra por degrau de NDBI (Landsat)

Estima `ano_inicio_obra` a partir da imagem, sem registro e sem classificador. É a peça L3→L4 do
diagrama: o "calibrador de obra" que devolve a data de início para o dataset de data centers,
para a amostra poder crescer sem alguém pesquisar o ano de cada caso à mão.

```
python datar_landsat.py --fase serie      # série anual de NDBI por campus (Earth Engine)
python datar_landsat.py --fase validar    # confere o método contra datas conhecidas
python datar_landsat.py --fase datar      # aplica e grava as datas derivadas
```

Precisa de credencial do Earth Engine (`EE_PROJECT` no `.env` da raiz) apenas na fase `serie`. As
fases `validar` e `datar` rodam sobre o CSV da série, offline.

## O método

Um data center aparece no OpenStreetMap como vários polígonos, um por prédio. `campi.py` agrupa
por proximidade (union-find, 2 km) e cada **campus** vira a unidade de datação — datar prédio a
prédio contaria o mesmo evento várias vezes.

Dentro do footprint do campus, mede-se um índice de construído no Landsat:

```
NDBI = (SWIR1 - NIR) / (SWIR1 + NIR)
```

O NDBI sobe quando vegetação ou solo viram superfície impermeável **e fica alto** — é degrau, não
pico. Obra em curso passa por solo exposto, que também levanta o índice; por isso o critério exige
que o nível se sustente depois, não só que suba num ano. `t0` é o ano que maximiza
(média de `t` em diante) − (média antes de `t`), com pelo menos 2 anos de cada lado e degrau acima
de 0,03. O degrau medido vai para a saída, então dá para reaplicar outro limiar sem reprocessar.

## ⚠ A validação não é favorável — leia antes de usar estas datas

A fase `validar` compara com 75 campi cuja data já era conhecida por outra via (Dynamic World).
Resultado da execução publicada aqui:

| métrica | valor |
|---|---|
| campi comparados | 75 (55 receberam data pelo Landsat também) |
| erro mediano | **−2,0 anos** |
| erro absoluto mediano | 2,0 anos |
| dentro de ±1 ano | **33%** |
| dentro de ±2 anos | 51% |

E na aplicação aos 482 campi, **284 ficaram sem degrau** — só 198 foram datados.

Ou seja: o método **data cedo demais, de forma sistemática**, e acerta o ano em um caso a cada
três. Não serve como está para definir pré/durante/pós de um estudo de evento — um erro de 2 anos
move a janela inteira. O que ele entrega hoje é um ordenamento grosseiro e um piso de comparação,
não uma data confiável.

Isso está migrado justamente por isso: a evidência de que o método ainda não serve é um resultado
do projeto, e fica versionada junto do código que a produziu. O viés negativo consistente sugere
que o degrau de NDBI marca o **início da terraplenagem** (solo exposto levanta o índice antes da
laje existir) e não o início da obra do prédio — o que aponta um caminho de correção, não um beco
sem saída.

## Entradas e saídas

| arquivo | camada | o que é |
|---|---|---|
| `dados/bronze/footprints_osm/eua_footprints_geom.json` | bronze | polígonos crus do OSM (entrada) |
| `dados/silver/datacao_obra/eua_datas_derivadas.csv` | silver | datação pelo Dynamic World — o gabarito da validação (entrada) |
| `dados/silver/datacao_obra/landsat_ndbi_serie.csv` | silver | série anual de NDBI por campus (6.266 linhas: 482 campi × 13 anos) |
| `dados/silver/datacao_obra/landsat_campi_meta.csv` | silver | um registro por campus: centroide, nome, operadora |
| `dados/silver/datacao_obra/landsat_datacao_validacao.csv` | silver | a comparação contra o Dynamic World, campus a campus |
| `dados/silver/datacao_obra/landsat_datas_derivadas.csv` | silver | a saída: `ano_obra_landsat`, `degrau_ndbi` e `status` por campus |

## Verificação da migração

Sem Earth Engine, porque as duas fases que decidem rodam sobre a série já publicada:

- **agrupamento em campi** — rodei `campi.py` sobre o footprint e comparei com o metadado
  publicado: **482 campi, os mesmos `campus_id`, na mesma ordem**, com diferença máxima de
  `0.0000000000` em lat e lon, e `nome`/`operadora` idênticos;
- **validação e datação** — rodei as fases `validar` e `datar` sobre `landsat_ndbi_serie.csv` e
  comparei com os CSVs publicados: **75 e 482 linhas, todas as colunas idênticas**.

Um detalhe que exigiu cuidado: `_dist_km` é haversine com R=6371, copiado como estava. O projeto
tem uma distância geodésica WGS84 mais exata em outro módulo, mas trocar poderia mover um prédio
de fronteira para outro campus e renumerar todos os `campus_id` — quebrando o vínculo com o que já
está publicado.

## Diferenças em relação ao original

- **Parâmetros saíram do código** para `parametros/params.yml`: coleções, escala de reflectância,
  meses do composto, janela, raio de agrupamento, critério de degrau e tamanho do lote.
- **`carregar_campi` virou módulo próprio** (`campi.py`). No original era um detalhe interno do
  passo que datava pelo Dynamic World, e o passo do Landsat o importava de lá — duas peças
  acopladas por um import lateral. Aqui a definição de "o que é um campus" é explícita, porque
  duas definições diferentes produziriam contagens incompatíveis sem ninguém notar.
- **Entradas e saídas pelo `config.py` da etapa**, em bronze e silver, em vez de caminhos fixos
  dentro de `modelo-impacto/raw/controles-rf/`.

## O que NÃO veio, e por quê

A outra metade da etapa 7 — **expandir a amostra de 15 para ~25 campi**
(`impacto_dc_25_expansao_amostra.py`) — depende de rodar a **inferência do Modelo 1** num raio
menor ao redor de cada ponto novo (`C.rodar_ponto`, `C.carregar_modelo`,
`C.caminho_classificado`) e do pareamento tratamento×controle. Nem o Modelo 1 nem o pareamento
estão migrados, então trazê-la agora significaria arrastar o núcleo do modelo de impacto junto.
Fica bloqueada até o Modelo 1 chegar.

Também vale registrar o universo: os 482 campi datados aqui são **americanos**, vindos do
levantamento de footprints do OSM. A datação da amostra brasileira usa o ano declarado no
datacentermap e, quando falta, é esta mesma técnica que teria de suprir — mas com a validação
acima resolvida antes.
