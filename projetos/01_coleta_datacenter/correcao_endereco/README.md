# correcao_endereco — sub-etapa 1 (pós-coleta)

Roda **depois** de `run_pipeline.py` (a coleta principal do datacentermap.com). Pega
`dados/bronze/datacentermap/datacentermap_datacenters.csv` e, pra cada linha, usa
`latitude`/`longitude` (sempre preenchidas) pra consultar a
[Google Geocoding API](https://developers.google.com/maps/documentation/geocoding) e obter
endereço, município, estado, país e CEP — em vez do texto livre que o operador digitou no
datacentermap.com (`endereco`, `cidade`, `estado`, `pais`, `cep` — inconsistentes, às vezes com
`estado` vazio mesmo tendo `cidade` preenchida).

## Estratégia: complementar x sempre atualizar (por campo)

Não é a mesma regra pra todo campo:

| Campo | Regra |
|---|---|
| `cidade` (município), `estado` (UF) | **Sempre atualizado** com o valor da Geocoding API (quando ela responde `OK`) — mesmo que o scraping já tivesse algo preenchido |
| `endereco`, `cep`, `pais` | **Só complementado** — o valor do scraping é mantido sempre que já existe; a API só entra pra preencher o que está vazio |

O porquê da diferença: `município`/`uf` é o que o Modelo 2 usa pra casar com o IBGE — vale mais
confiar sempre no geocoding do que no que foi digitado. Já `endereco`/`cep`/`pais` não têm um
consumidor downstream tão sensível a padronização, então não vale a pena perder informação que o
scraping já trouxe certa só pra substituir pela versão do Google.

## Por que isso importa pro resto do pipeline

O Modelo 2 (grupo de controle) casa `município`/`uf` de cada data center com o perfil do IBGE via
KNN — se esses campos vierem digitados de forma inconsistente, o pareamento erra ou falha
silenciosamente. Corrigir aqui, logo depois da coleta, evita que esse problema se espalhe pro
resto do pipeline.

## Limpeza aplicada

- Trim de espaço em branco de toda coluna de texto do CSV bruto (ex.:
  `"R. da Independencia, 632 "`, com espaço sobrando no fim).
- Linhas sem `latitude`/`longitude` não chamam a API — ficam com `status_geocode =
  "LAT_LON_AUSENTE"`, e os campos de endereço continuam exatamente como vieram do scraping.
- O CSV de saída usa **os mesmos nomes de coluna do bronze** (`endereco`, `cidade`, `estado`,
  `pais`, `cep`) — não cria colunas `_corrigido` paralelas; `municipio`/`estado` são sobrescritos
  in-place, os outros três são só preenchidos onde estavam vazios.
- `status_geocode` (`OK` / `ZERO_RESULTS` / `LAT_LON_AUSENTE` / `ERRO_REDE: ...` / `ERRO_API:
  ...`) fica registrado por linha — falha de geocoding não derruba a linha do data center, só
  deixa os campos como já estavam no scraping.

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

