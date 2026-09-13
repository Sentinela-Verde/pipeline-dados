# correcao_endereco — sub-etapa 1 (pós-coleta)

Roda **depois** de `run_pipeline.py` (a coleta principal do datacentermap.com). Pega
`dados/bronze/datacentermap/datacentermap_datacenters.csv` e, pra cada linha, usa
`latitude`/`longitude` (sempre preenchidas) pra consultar a
[Google Geocoding API](https://developers.google.com/maps/documentation/geocoding) e obter
**endereço, município, estado, país e CEP padronizados** — em vez do texto livre que o operador
digitou no datacentermap.com (`endereco`, `cidade`, `estado`, `pais`, `cep` — inconsistentes,
às vezes com `estado` vazio mesmo tendo `cidade` preenchida).

## Por que isso importa pro resto do pipeline

O Modelo 2 (grupo de controle) casa `município`/`uf` de cada data center com o perfil do IBGE via
KNN — se esses campos vierem digitados de forma inconsistente, o pareamento erra ou falha
silenciosamente. Corrigir aqui, logo depois da coleta, evita que esse problema se espalhe pro
resto do pipeline.

## Limpeza aplicada

- Trim de espaço em branco de toda coluna de texto do CSV bruto (ex.:
  `"R. da Independencia, 632 "`, com espaço sobrando no fim).
- Linhas sem `latitude`/`longitude` não chamam a API — ficam com `status_geocode =
  "LAT_LON_AUSENTE"`, mas **não são descartadas**.
- **As colunas antigas de endereço (`endereco`, `cep`, `cidade`, `estado`, `pais`) são removidas**
  do resultado final — o CSV de saída fica só com as versões padronizadas
  (`endereco_corrigido`, `municipio_corrigido`, `estado_corrigido`, `pais_corrigido`,
  `cep_corrigido`) + `status_geocode`, nunca as duas versões lado a lado.
- `status_geocode` (`OK` / `ZERO_RESULTS` / `LAT_LON_AUSENTE` / `ERRO_REDE: ...` / `ERRO_API:
  ...`) fica registrado por linha — falha de geocoding não derruba a linha do data center, só
  deixa as colunas de endereço vazias pra essa linha específica.

## Como rodar

```bash
cd projetos/01_coleta_datacenter/correcao_endereco
pip install -r requirements.txt
python step7_corrige_endereco.py
```

Precisa de `GOOGLE_MAPS_API_KEY` no `.env` da raiz do repositório (`pipeline-dados/.env` — copie
de `.env.example`), com a Geocoding API habilitada e faturamento ativo no projeto do Google Cloud
correspondente. Uma chamada de API por linha — confira o tamanho do CSV de entrada antes de rodar
(hoje 242 data centers), já que cada chamada consome cota paga.

- **Entrada:** `dados/bronze/datacentermap/datacentermap_datacenters.csv`
- **Saída:** `dados/silver/datacentermap_enderecos_corrigidos.csv`

## Origem

Esta sub-etapa é uma readaptação de `data-extraction/transform/pega_endereco/` — a lógica de
reverse geocoding é a mesma, mas lá a entrada é `lista_mestra_campi.csv` (uma lista mais ampla,
gerada por um script do `modelo-imagens-satelite` que combina candidatos de várias fontes,
inclusive expansão EUA). Aqui a entrada foi trocada pra ler direto o CSV desta coleta
(`datacentermap_datacenters.csv`), pra fechar a etapa 1 sem depender do outro repositório — ver
decisão 7 do README da raiz.
