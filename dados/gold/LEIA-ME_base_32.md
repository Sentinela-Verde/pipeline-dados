# Base final 32 data centers (BR + EUA) — 2026-09-14

## Arquivos

- **`base_final_32_dc_br_eua.csv`** — 428 linhas. É a base unificada: 31 tratamentos
  (15 BR + 16 EUA) e 31 controles pareados, com classes por ano.
- `base_eua_classes_por_ano.csv` — 224 linhas, só o lado americano (32 pontos × 7 anos).
- Gerador: `projetos/07_reiteracao_expansao_amostra/base_eua_dw/gerar_base_eua.py`.

## ⚠ Os dois lados vêm de instrumentos diferentes

A coluna **`instrumento`** diz de onde cada linha saiu, e isso não é detalhe:

| lado | instrumento | resolução |
|---|---|---|
| Brasil | `rf_v1.0-tuned` (o classificador do projeto) | 30 m / 10 m |
| EUA | `dynamic_world` (remapeado para as 5 classes pelo `classes.yml`) | 20 m |

Classificar os campi americanos com o Random Forest exigiria ingerir imagem, montar o stack de
features e rodar inferência para 224 site-anos — horas de Earth Engine. O Dynamic World é global,
já tem classe, e o projeto **já usa o remap dele** como fonte de rótulo desde 2026-09-11.

**Consequência prática:** compare BR com BR e EUA com EUA. Comparar o nível absoluto de uma classe
entre os dois lados mistura a diferença real com a diferença de instrumento — a mesma armadilha
que a validação cruzada de sensores resolveu para Landsat × Sentinel-2, e que aqui não foi feita.
O que é comparável entre os dois lados é a **variação relativa** de cada ponto contra o seu próprio
controle.

## Como os campi americanos foram escolhidos

Dos 482 campi com footprint no OSM, ficaram os que têm data de obra **e** janela obra±3 dentro da
cobertura do Dynamic World (2016-2025), ou seja obra entre 2019 e 2022. Priorizei data validada
pelo DW sobre data por degrau de NDBI no Landsat, campus maior, e um filtro de 30 km entre campi
para não pegar dois do mesmo cluster urbano.

A coluna **`fonte_data_obra`** registra qual datação vale em cada linha. `landsat_ndbi` tem erro
mediano de −2,0 anos (validado contra 75 campi), então a janela pré/durante/pós dessas linhas é
aproximada. `dynamic_world` é a datação validada.

## Controles

Ponto a **15 km** do campus, no primeiro azimute (varredura de 15°) que fica a pelo menos 10 km de
qualquer outro data center conhecido da lista de 488. É o mesmo desenho de anel da metodologia
brasileira, sem a checagem de similaridade de cobertura pré-obra — não havia tempo. Por isso a
coluna `qualidade_par` está vazia do lado americano.

## Sinal, para conferência rápida

Área construída, média dos anos t+2/t+3 menos a média do período pré:

- tratamento: mediana **+1,80 pp** (n=16)
- controle: mediana **+0,51 pp** (n=16)
- o tratamento cresce mais que o seu controle em **13 dos 16 pares**

Não é teste estatístico — é sanidade. As proporções somam 1,00 em todas as 428 linhas.
