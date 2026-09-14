# dados/silver/sites_referencia/

Snapshots versionados da lista de **16 AOIs curadas manualmente** (`modelo-imagens-satelite`,
SV-24/SV-25) — a lista de referência que `projetos/02_extracao_imagem/`, `03_extracao_labels/` e
`04_indices_espectrais/` usam via `parametros/sites.geojson` para saber quais sites processar.

**Não confundir com os 21 AOIs de `dados/silver/datacenter_filtrado.csv`** — são duas fontes
diferentes, com processos e propósitos diferentes:

| | 16 curados (esta pasta) | 21 do scraping |
|---|---|---|
| Formato | GeoJSON (`Point` + properties) | CSV (`;`) |
| Origem | Curadoria manual + pesquisa web (SV-24/25) sobre 38 candidatos do Notion | Filtro automático + dedup por proximidade sobre 242 registros do DataCenterMap |
| Critério de seleção | Elegibilidade E1-E4 + diversidade de bioma/era de sensor (tier 1/2) | status/stage/ano/tipo + mesmo operador ≤600m |
| Validação de coordenada | Cascata V1-V5 (PeeringDB/OSM/MapBiomas/colisão/distância) | Nenhuma — lat/lon vem direto do scraping |
| Uso hoje | Entrada de `02_extracao_imagem`, `03_extracao_labels`, `04_indices_espectrais` | Entrada de `modelo_2_grupo_controle` (pareamento com grupo controle) |

## Arquivos

- **`sites_16_curados_rodada2_2026-09-01.geojson`** — snapshot da versão usada em
  **ADR-005 rodada 2** (`modelo-imagens-satelite/docs/decisoes/ADR-005-expansao-de-sites.md`,
  atualizado em 2026-09-01): 16 AOIs elegíveis (13 tier 1 + 3 tier 2), cobrindo 4 biomas
  (Mata Atlântica, Caatinga, Cerrado, Amazônia). Idêntico, no momento deste snapshot, às cópias em
  `projetos/03_extracao_labels/parametros/sites.geojson` e
  `projetos/04_indices_espectrais/parametros/sites.geojson` (a cópia em `02_extracao_imagem` tem 1
  linha a mais, `ascenty-hortolandia-htl5`, adicionada à parte para a amostra de extração real —
  ver ressalva abaixo).

## Por que isso é um snapshot versionado, não a fonte viva

As 3 cópias em `projetos/*/parametros/sites.geojson` são a fonte que o **código** lê — se a lista
mudar (nova rodada de curadoria, correção de coordenada via SV-25), essas cópias são atualizadas
no lugar. Este arquivo aqui, em vez disso, é **imutável**: registra qual versão exata da lista foi
usada nesta rodada de processamento (o `_2026-09-01` no nome é a data da rodada, não a data em que
o snapshot foi tirado). Uma futura curadoria (rodada 3, mudança de tier, etc.) ganha um novo
arquivo aqui (`sites_16_curados_rodada3_...json`) em vez de sobrescrever este — histórico de qual
lista gerou qual resultado fica rastreável mesmo depois que `parametros/sites.geojson` mudar.

## Inconsistência conhecida (não corrigida neste snapshot)

`projetos/02_extracao_imagem/parametros/sites.geojson` tem 17 sites (16 + `ascenty-hortolandia-htl5`,
que na verdade é uma FACILITY do scraping, não uma AOI curada — foi adicionada ali só para a
extração de amostra real feita em sessão anterior). As cópias em `03_extracao_labels` e
`04_indices_espectrais` (e este snapshot) não têm essa linha. Ver `filtro_elegibilidade/README.md`
para o AOI equivalente na lista dos 21 (`ascenty-data-centers-hortolandia`).
