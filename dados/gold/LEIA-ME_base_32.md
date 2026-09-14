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

---

# Enriquecimento das colunas de contexto (2026-09-14, segunda rodada)

## O que foi preenchido no lado americano

| coluna | fonte | observação |
|---|---|---|
| `municipio` | US Census Geocoder | é o **condado**, análogo do município |
| `uf` | FIPS do condado → sigla do estado | offline, sem API |
| `codigo_ibge` | **FIPS** de 5 dígitos (estado+condado) | mesmo papel do código IBGE: chave oficial de geografia |
| `regiao` | divisão censitária do estado | Northeast / Midwest / South / West |
| `bioma` | RESOLVE Ecoregions 2017 (moda no buffer) | nomes traduzidos |
| `lst_media_celsius` | MODIS MOD11A2, média anual no buffer | **mesmo instrumento e mesmo método do lado brasileiro** |
| `l1_rf` / `qualidade_par` | distância L1 entre as proporções médias do período pré do tratamento e do seu controle | limiares de SV-29: bom ≤ 0,10 · aceitável ≤ 0,20 · ruim acima |
| `populacao_buffer_5km` | GHSL GHS-POP 2020, soma no buffer | **coluna nova, calculada igual nos dois países** |

## ⚠ O pareamento americano é fraco, e a coluna diz isso

Dos 16 pares americanos: **14 ruins, 1 aceitável, 1 bom**. O controle foi gerado pelo anel de
15 km sem a checagem de similaridade de cobertura pré-obra que o desenho brasileiro faz — e o
resultado é que, na maioria dos casos, o ponto de controle não se parece com o tratamento antes da
obra. Para diferença-em-diferenças isso é limitante: um par ruim mede tanto a diferença de partida
quanto o efeito.

Use `qualidade_par` para filtrar antes de concluir qualquer coisa. Melhorar isso é gerar vários
candidatos por azimute e escolher o de menor L1 — é o que o lado brasileiro faz, e cabe numa
próxima rodada.

## O que ficou vazio, e por quê

- **`populacao`** — ✅ **preenchida** (2026-09-14, terceira rodada): ACS 5-year de 2022, variável
  `B01003_001E`, população do **condado** — 26 condados distintos para os 32 pontos. A coluna
  `populacao_tipo_estimativa` diz a origem linha a linha: `ACS 2022 5-year (condado)` nos EUA,
  IBGE no Brasil. A chave do Census fica na variável de ambiente `CENSUS_API_KEY`, nunca no código
  nem no CSV.

  Atenção à unidade: são populações de recortes administrativos de tamanhos muito diferentes
  (condado americano × município brasileiro). Para comparar densidade ou pressão populacional no
  entorno, use `populacao_buffer_5km`, que é o mesmo recorte de 5 km nos dois países.
- **`pib_mil_reais`** — PIB por condado é do BEA (tabela CAGDP2), que pede uma chave própria,
  diferente da do Census. Único campo de contexto que segue vazio do lado americano, junto do
  `tier`.
- **`tier`** — não existe para os campi americanos: o `datacentermap` responde HTTP 429 para
  raspagem em volume (ADR-006 §7), e os campi americanos vieram do OpenStreetMap, que não traz tier.

## E no lado brasileiro

`tier`, `regiao` e `bioma` estavam preenchidos só nas linhas de tratamento (102 de 204). Os
controles agora herdam do seu par — o que é correto por construção: o controle fica no mesmo
recorte regional do tratamento, é esse o desenho.


## Reprodução

Os três scripts que geraram e completaram esta base estão em
`projetos/07_reiteracao_expansao_amostra/base_eua_dw/`:

1. `gerar_base_eua.py` — seleção dos campi, controles e classes por ano (Dynamic World);
2. `enriquecer32.py` — geografia, bioma, LST e L1/qualidade do par;
3. `enriquecer_pass2.py` — UF/região pelo FIPS e população no buffer (GHSL);
4. `preencher_pop.py` — população do condado (ACS; lê `CENSUS_API_KEY` do ambiente).
