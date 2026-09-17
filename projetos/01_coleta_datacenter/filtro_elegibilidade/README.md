# filtro_elegibilidade — sub-etapa 1 (pós-coleta, encadeada depois de `correcao_endereco/`)

Dois steps, rodados em sequência, encadeados depois de `correcao_endereco/` (que por sua vez roda
depois de `run_pipeline.py`):

```
run_pipeline.py             -> dados/bronze/datacentermap/datacentermap_datacenters.csv
correcao_endereco/          -> dados/silver/datacentermap_enderecos_corrigidos.csv
step8_filtra_elegibilidade.py -> dados/silver/datacenter_filtrado_facilities.csv   (1 linha/facility)
step9_consolida_aoi.py        -> dados/silver/datacenter_filtrado.csv             (1 linha/AOI — final)
```

## step8 — filtro de elegibilidade

Pega o CSV já com endereço/município/estado padronizados e filtra só os data centers que servem
pro estudo de impacto.

### Critério de elegibilidade

Um data center entra no estudo se:

- **`status == 1`** — está ativo (não descontinuado/planejado).
- **`stage == 2`** — já foi construído (não é só projeto anunciado).
- **`tipo_listagem == 'Facility'`** — exclui listagens de "Campus" e "Multi-Tenant Building".
- **`ano_operacional`** entre **2018 e 2024** (exclusive nas pontas — ver
  `config.ANO_OPERACIONAL_MIN`/`MAX`).

O motivo da janela de anos: a análise estatística (`projetos/09_analise_estatistica_impacto/`)
mede o efeito numa janela móvel ao redor do ano de abertura (ano-3 até ano+2).

**Saída:** `dados/silver/datacenter_filtrado_facilities.csv` — 1 linha por facility elegível
(`nome_datacenter`, `operadora`, `endereco`, `cidade`, `latitude`, `longitude`, `tags`,
`mw_construido`, `whitespace_construido_m`, `ano_operacional`, `tipo_construcao`). **Não é o
artefato final** — várias facilities do mesmo operador podem ser o mesmo campus.

## step9 — consolidação por AOI

Facilities do **mesmo operador** a até **`config.RAIO_MESMO_AOI_M` (600 m)** de distância viram
**1 AOI só** (600 m identifica "é o mesmo campus"; a extração de imagem de satélite, mais adiante,
usa um raio maior em torno do AOI já consolidado). Exemplo real: `Ascenty - Hortolandia
HTL2/3/4/5` são 4 facilities do scraping, 1 AOI só (mesmo campus).

### `ano_inicio_obra` por AOI

Nesta ordem de prioridade:

1. **Pesquisado** — se existe uma linha pra `(operadora, cidade)` em
   `dados/bronze/datacentermap/aoi_construcao_pesquisada.csv` (ver README daquela pasta pra como
   essa pesquisa foi feita/reaproveitada). Hoje cobre **9 dos 21 AOIs**.
2. **Projetado** — senão, `ano_inicio_obra = ano_operacional_min do AOI −
   config.ANOS_PROJECAO_INICIO_OBRA` (parâmetro, hoje **3**). Cobre os outros **12 AOIs**. Nunca
   fica em branco, mas fica marcado (`metodo_ano_inicio_obra = "projecao"`) pra quem for usar
   saber que não é pesquisa de verdade.

Porte (`mw_construido`, `whitespace_construido_m`) é **somado** entre as facilities do mesmo AOI
— representa o campus inteiro, não 1 prédio.

**Saída (artefato final desta sub-etapa):** `dados/silver/datacenter_filtrado.csv` — colunas
`aoi_id`, `operadora`, `cidade`, `n_facilities`, `facilities` (lista `; `-separada dos nomes
originais), `latitude`/`longitude` (média do grupo), `mw_construido_total`,
`whitespace_construido_m_total`, `ano_operacional_min`/`max`, `ano_inicio_obra`,
`metodo_ano_inicio_obra` (`pesquisa_reaproveitada` | `projecao`), `confianca_ano_inicio_obra`
(`alta`/`media`/`baixa`), `fonte_ano_inicio_obra`.

**Resultado atual:** 29 facilities elegíveis → **21 AOIs** (9 com `ano_inicio_obra` pesquisado, 12
projetado).

## Como rodar

```bash
cd projetos/01_coleta_datacenter/filtro_elegibilidade
pip install -r requirements.txt
python step8_filtra_elegibilidade.py
python step9_consolida_aoi.py
```

## Quem consome essa saída

- `modelos/modelo_2_grupo_controle/` — pareia cada AOI (por `aoi_id`) com um grupo de controle.
- `projetos/02_extracao_imagem/` — usa `aoi_id`/`latitude`/`longitude` como lista de pontos a
  extrair do Google Earth Engine.

Nota de schema: a chave de `datacenter_filtrado.csv` é `aoi_id` (1 por campus), diferente de
`datacenter_filtrado_facilities.csv`, que é 1 linha por facility (`nome_datacenter`) — use o
arquivo certo conforme a granularidade que precisar.

Ver `dados/bronze/datacentermap/README.md` para como a pesquisa de `ano_inicio_obra` foi feita.

## Por que ainda sem `estado` no schema de facilities

`config.COLUNAS_FINAIS` (usado pelo step8) não inclui `estado`, mesmo ele já vindo confiável de
`correcao_endereco/` — mantém compatibilidade com quem ainda lê
`datacenter_filtrado_facilities.csv` no formato antigo. Se for útil, é só adicionar `"estado"` lá.
