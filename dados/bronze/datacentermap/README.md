# dados/bronze/datacentermap/

- `datacentermap_datacenters.csv`, `pais/`, `regioes/`, `datacenters/` — saída bruta do scraping
  (`projetos/01_coleta_datacenter/`, steps 1-6).
- **`aoi_construcao_pesquisada.csv`** — pesquisa de **ano de início de obra por AOI**
  (operador + cidade), usada por
  `projetos/01_coleta_datacenter/filtro_elegibilidade/step9_consolida_aoi.py` pra decidir o
  `ano_inicio_obra` de cada AOI consolidada. É dado **de pesquisa** (não do scraping), por isso
  fica na bronze como insumo — não é gerado por nenhum script deste repositório.

## `aoi_construcao_pesquisada.csv`

| Coluna | O que é |
|---|---|
| `operadora`, `cidade` | Chave de junção com o AOI consolidado (mesma normalização do step9) |
| `ano_construcao_min` | Ano de início de obra pesquisado (o mais antigo, se o AOI tem vários prédios) |
| `metodo` | `pesquisa_reaproveitada` (veio de outra fonte já pesquisada) ou `pesquisa_nova` (pesquisado do zero pra este repositório) |
| `confianca` | `alta` (fonte primária: página do operador, PeeringDB) / `media` (fonte secundária ou cobre só parte do AOI) / `baixa` (número existe mas sem link de fonte rastreável) |
| `fonte_url` | Link da fonte, quando existe |
| `observacao` | Ressalvas — leia antes de confiar cegamente no número |

**Hoje cobre 9 dos 21 AOIs** (pesquisa feita e citada por fonte primária). Os outros 12 AOIs não
têm linha aqui — `step9_consolida_aoi.py` **projeta** o ano pra esses (`ano_operacional_min −
config.ANOS_PROJECAO_INICIO_OBRA`), não deixa em branco. Pesquisar esses 12 de verdade (imprensa,
releases, PeeringDB) é o próximo passo natural pra reduzir quanto do painel final depende de
projeção em vez de fonte primária.

**AOIs sem pesquisa ainda** (usam projeção): ODATA (São João de Meriti), ODATA (Hortolândia —
existe como AOI conhecida em `sites_candidatos.csv`, mas sem ano documentado nem lá), ASAP
Telecom, Ascenty (Rio de Janeiro RJ2), Hosting Now (Curitiba), IDX (Palmas), IPXON (Maracanaú,
Rio de Janeiro, São Paulo), Quântico (Canoas), TO HOST (Palmas), Netwise (Lagoa da Prata).
