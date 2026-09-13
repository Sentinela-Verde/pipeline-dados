# scraping_datacentermap — coleta do datacentermap.com

Pipeline de scraping organizado em steps bem definidos, com cache
incremental em disco, para não precisar reprocessar tudo a cada execução.
É uma das coletas dentro de `data-extraction/extract/` — ver o
[README da raiz](../../README.md) pra entender como as coletas se encaixam
(pasta `data/raw/` compartilhada).

## Ideia geral

As páginas do datacentermap.com são Next.js e trazem os dados já prontos em
JSON dentro de `<script id="__NEXT_DATA__">` — não precisamos guardar o HTML
inteiro nem depender de seletores CSS (`<div class="header">` etc., que
quebram fácil). Cada step de scraping abre a página, tira só o JSON que
interessa, e salva um arquivo pequeno em `../../data/raw/datacentermap/` (ver
seção própria abaixo). Os outros steps só leem isso localmente.

Entrada única do pipeline: `config.PAIS` (hoje `"brazil"`), de onde sai a URL
`https://www.datacentermap.com/{PAIS}/`.

## Estrutura de pastas

O código é organizado por nível da árvore que é raspada — país → região →
datacenter — cada um na sua pasta, com o step que busca (Selenium) e o step
que processa (local) lado a lado:

```
data-extraction/
├── data/raw/
│   ├── datacentermap/          # dado bruto extraído (= o cache) — compartilhado, ver README da raiz
│   │   ├── pais/
│   │   ├── regioes/
│   │   └── datacenters/
│   └── outputs_extraction/     # CSVs finais de todas as coletas
│       └── datacentermap_datacenters.csv
└── extract/
    └── scraping_datacentermap/    # <- você está aqui
        ├── config.py              # país, caminhos, delays — a única coisa que normalmente se muda
        ├── run_pipeline.py        # roda tudo (ou uma etapa) na ordem certa
        ├── comum/                 # código compartilhado pelos steps desse coletor
        │   ├── cache_store.py     #   ler/gravar data/raw (o cache)
        │   └── next_data.py       #   extrair __NEXT_DATA__ e detectar bloqueio
        ├── pais/
        │   ├── step1_scrape_pais.py       # Selenium: lista de regiões do país
        │   └── step2_montar_regioes.py    # local: monta output/regioes.csv
        ├── regioes/
        │   ├── step3_scrape_regioes.py            # Selenium: datacenters de cada região
        │   └── step4_montar_links_datacenters.py  # local: monta output/datacenters_links.csv
        ├── datacenters/
        │   ├── step5_scrape_datacenters.py  # Selenium: overview + specs de cada datacenter
        │   └── step6_build_csv.py           # local: monta o CSV final em ../../data/raw/outputs_extraction/
        └── output/                 # CSVs intermediários (só interessam a essa coleta)
            ├── regioes.csv
            └── datacenters_links.csv
```

```
.
├── https://www.datacentermap.com/brazil/            -> pais/step1 (Selenium) + pais/step2 (junta)
│   ├── .../porto-alegre/                             -> regioes/step3 (Selenium) + regioes/step4 (junta)
│   │   ├── .../porto-alegre/elea-digital-poa1/       -> datacenters/step5 (Selenium: overview + specs)
│   │   └── .../porto-alegre/elea-digital-poa2/       -> datacenters/step5
│   ├── .../sao-paulo/
│   └── ...                                                datacenters/step6 monta o CSV final
```

Trocar `config.PAIS` (ex.: para outro país listado no datacentermap.com) roda
o mesmo pipeline pra outro lugar, sem mudar nenhum step.

## `data/raw/datacentermap/` — o dado bruto extraído (e o cache)

Cada item (o país, uma região, ou uma aba de um datacenter) vira um `.json`
com um `status`: `ok`, `bloqueado` (tomou rate limit) ou `erro`. É esse mesmo
arquivo que funciona como cache: rodar um step de novo **pula
automaticamente** tudo que já está `ok` — só tenta de novo o que faltou ou
que foi bloqueado da última vez.

```
data/raw/datacentermap/
├── pais/
│   └── brazil.json
├── regioes/
│   └── porto-alegre.json
└── datacenters/
    ├── elea-digital-poa1__overview.json
    ├── elea-digital-poa1__specs.json
    ├── elea-digital-poa2__overview.json
    └── elea-digital-poa2__specs.json
```

Formato de `pais/brazil.json` (resumido — `geos` tem uma entrada por região
do país):

```json
{
  "status": "ok",
  "atualizado_em": "2026-09-07T13:40:00",
  "tentativas": 1,
  "dados": {
    "geodata": { "name": "Brazil", "meta_stats": { "dcs": { "operators": 73 } } },
    "geos": [
      { "link": "porto-alegre", "name": "Porto Alegre", "datacenters": 15, "latitude": -30.03, "longitude": -51.23 }
    ]
  }
}
```

Formato de `regioes/porto-alegre.json` (resumido — `dcs` tem uma entrada por
datacenter da região):

```json
{
  "status": "ok",
  "atualizado_em": "2026-09-07T13:41:00",
  "tentativas": 1,
  "dados": {
    "geodata": { "name": "Porto Alegre", "meta_stats": { "dcs": { "mw_live": 12.4, "operators": 9 } } },
    "dcs": [
      {
        "id": 12345,
        "link": "elea-digital-poa1",
        "name": "Elea Digital POA1",
        "url": "/brazil/porto-alegre/elea-digital-poa1/",
        "companylink": "elea-digital",
        "companyname": "Elea Digital",
        "city": "Porto Alegre",
        "address": "...",
        "listingtype": "Facility",
        "capacitytype": "Colocation",
        "latitude": -30.03,
        "longitude": -51.23
      }
    ]
  }
}
```

Formato de `datacenters/elea-digital-poa1__overview.json` (o bloco `dc` é o
mesmo que vira colunas no CSV final — ver `datacenters/step6_build_csv.py`):

```json
{
  "status": "ok",
  "atualizado_em": "2026-09-07T13:42:00",
  "tentativas": 1,
  "dados": {
    "tab": "overview",
    "dc": {
      "id": 12345,
      "link": "elea-digital-poa1",
      "name": "Elea Digital POA1",
      "address": "...",
      "city": "Porto Alegre",
      "market": "Porto Alegre",
      "country": "Brazil",
      "latitude": -30.03,
      "longitude": -51.23,
      "description": "...",
      "status": 1,
      "stage": 1,
      "listingtype": "Facility",
      "capacitytype": "Colocation",
      "meta_power": { "totalmw": "12", "cooling_redundancy": "N+1" },
      "meta_capacity": { "mw_builtout": 12, "mw_referenced": 12 },
      "meta_references": { "provider_id": "POA1", "peeringdb_id": 11612 },
      "companies": { "name": "Elea Digital" }
    },
    "serviceplan": {
      "services": {
        "colo": { "suites": 0, "cages": 1, "cabinets": 12 },
        "cloud": {}
      }
    }
  }
}
```

A versão `..._specs.json` tem a mesma forma, só que com `meta_standards`,
`meta_security` e `meta_building` preenchidos em vez de `meta_power`, e
`serviceplan: null` (só vem na aba overview) — é por isso que o
`step6_build_csv.py` mescla os dois `dc` (`deep_merge_preferindo`) em vez de
usar só um deles, e pega `serviceplan` só do overview.

## Cache incremental

Rodar um step de novo **pula automaticamente** tudo que já está `ok` em
`data/raw/datacentermap/` — só tenta de novo o que faltou ou que foi
bloqueado da última vez. Isso quer dizer que dá pra:
- Parar o processo no meio (Ctrl+C, queda de conexão, PC desligou) e
  continuar de onde parou depois, sem perder o que já foi baixado.
- Rodar só os steps de Selenium (1, 3, 5) num dia e os locais (2, 4, 6) —
  instantâneos — em outro.
- Usar `--forcar` quando quiser ignorar o cache e buscar tudo de novo.

Rate limit ("Page View Limit Reached") é detectado explicitamente
(`comum/next_data.esta_bloqueado`) e tratado como falha — não fica salvo no
cache como se fosse um dado válido, e é buscado de novo automaticamente.

## Como rodar

Primeira vez:

```bash
cd data-extraction/extract/scraping_datacentermap
pip install -r requirements.txt
```

Todos os comandos abaixo rodam a partir dessa pasta.

### Rodar full (país inteiro)

```bash
python run_pipeline.py
```
Executa os 6 steps em ordem. Como usa cache incremental, rodar de novo é
sempre seguro: só busca o que ainda falta (nunca buscado, `bloqueado` ou
`erro`). Pra ignorar o cache e buscar tudo de novo: `python run_pipeline.py --forcar`.

### Rodar teste rápido (1 região + poucos datacenters)

```bash
python run_pipeline.py --teste
```
Atalho pra `--limite-regioes 1 --limite-datacenters 3` (valores em
`config.TESTE_LIMITE_REGIOES`/`TESTE_LIMITE_DATACENTERS`) — roda a sequência
completa país → região → datacenter gastando poucas requisições. Dá pra
ajustar os números na hora, sem editar `config.py`:

```bash
python run_pipeline.py --limite-regioes 1 --limite-datacenters 3
python run_pipeline.py --teste --limite-datacenters 5   # --teste + um valor específico só pro step 5
```
(um `--limite-*` explícito sempre vence sobre o `--teste`)

### Rodar separado (uma etapa por vez)

```bash
python run_pipeline.py --so step1   # ou step2, step3, step4, step5, step6
```
equivale a rodar o arquivo do step direto (funciona de qualquer diretório):
```bash
python pais/step1_scrape_pais.py
python pais/step2_montar_regioes.py
python regioes/step3_scrape_regioes.py [--limite N] [--forcar]
python regioes/step4_montar_links_datacenters.py
python datacenters/step5_scrape_datacenters.py [--limite N] [--forcar]
python datacenters/step6_build_csv.py
```

Cada step depende do que o anterior gerou — rodar um sozinho só funciona se
isso já está em disco (rodar `run_pipeline.py` inteiro sempre funciona,
porque ele pula direto pro que falta):

| Step | Arquivo | Precisa que já exista |
|---|---|---|
| 1 | `pais/step1_scrape_pais.py` | nada |
| 2 | `pais/step2_montar_regioes.py` | `data/raw/datacentermap/pais/<pais>.json` (do step 1) |
| 3 | `regioes/step3_scrape_regioes.py` | `output/regioes.csv` (do step 2) |
| 4 | `regioes/step4_montar_links_datacenters.py` | `data/raw/datacentermap/regioes/*.json` (do step 3) |
| 5 | `datacenters/step5_scrape_datacenters.py` | `output/datacenters_links.csv` (do step 4) |
| 6 | `datacenters/step6_build_csv.py` | `output/datacenters_links.csv` (do step 4) + `data/raw/datacentermap/datacenters/*.json` (do step 5) |

Cada step também pode ser aberto e rodado célula-a-célula num notebook, se
preferir — são só funções `main()` sem estado escondido em variável de
notebook.

### Importar HTMLs já baixados (sem rodar o Selenium)

Se você já tem uma pasta de HTMLs salvos por fora (`regiao_<slug>.html` e
`datacenter_<slug>[_specs].html`), dá pra importar direto pro
`data/raw/datacentermap/` sem gastar nenhuma requisição nova:

```bash
python importar_html.py --regioes "caminho/para/html_regiao" --datacenters "caminho/para/html_datacenter"
```

Detecta página de rate limit ("Page View Limit Reached") igual aos steps 2/4
e marca como `bloqueado` em vez de `ok`, então uma rodada normal do step 5
(com `--forcar` só pros que precisam) completa o que faltou. Depois de
importar, rode `step4_montar_links_datacenters.py` e `step6_build_csv.py`
(ou `run_pipeline.py --so step4` / `--so step6`) pra atualizar os CSVs.

## Saídas

- `output/regioes.csv` — as regiões do país e seus links (intermediário).
- `output/datacenters_links.csv` — todos os datacenters únicos encontrados,
  com o link de cada um (intermediário).
- `../../data/raw/outputs_extraction/datacentermap_datacenters.csv` — o resultado final, um
  datacenter por linha (`;` como separador, `utf-8-sig`, abre certo no
  Excel). Colunas, na ordem:

  | Grupo | Colunas |
  |---|---|
  | Identificação | `nome_datacenter`, `operadora`, `endereco`, `cep`, `cidade`, `estado`, `pais`, `latitude`, `longitude`, `status`, `stage`, `tipo_listagem`, `tipo_capacidade`, `tags`, `link_datacenter` |
  | Capacidade | `mw_construido`, `mw_referenciado`, `whitespace_construido_m`, `whitespace_referenciado_m` |
  | Prédio | `ano_operacional`, `tipo_construcao`, `tipo_ocupacao`, `carga_piso_max_kg_m` |
  | Energia/refrigeração | `redundancia_refrigeracao` |
  | Segurança | `cctv`, `controle_acesso_cartao`, `biometria` |
  | Certificações | `tier_projetado`, `tier_certificado`, `pci_dss`, `iso9001`, `iso14001`, `iso22301`, `iso27001`, `iso45001`, `iso50001`, `soc1`, `soc2`, `soc3` |
  | Colocation (`serviceplan.services.colo`, só na aba overview) | `colo_suites`, `colo_cages`, `colo_cabinets`, `colo_partial_cabinets`, `colo_shared_rackspace`, `colo_footprints`, `colo_remote_hands`, `colo_build_to_suit` |
  | Cloud (`serviceplan.services.cloud`, só na aba overview) | `cloud_gpu`, `cloud_managed`, `cloud_baremetal`, `cloud_public_cloud` |
  | Contadores (`meta_stats`) | `qtd_ixps`, `qtd_clouds`, `qtd_redes_presentes`, `qtd_provedores_rede`, `qtd_provedores_servico` |
  | Referências externas (`meta_references`) | `codigo_site`, `peeringdb_id` |
  | Diagnóstico | `cache_overview_status`, `cache_specs_status` — filtre por essas duas pra ver quais linhas ainda estão incompletas (precisam do step 5 de novo) |

  Os nomes de chave dos planos de `colo_remote_hands`/`colo_build_to_suit`/
  `cloud_*` foram inferidos pelo padrão dos outros campos de `colo` (nunca
  vimos um datacenter real com esses planos preenchidos pra confirmar) — pode
  precisar de ajuste se aparecerem errados numa extração real.

  **Atenção**: `colo_*`/`cloud_*` só saem preenchidos pra datacenters
  raspados **depois** dessa mudança — entradas de `data/raw/datacentermap/datacenters/`
  raspadas antes não têm `serviceplan` salvo. Rode `--forcar` no step 5 pra
  essas se quiser essas colunas completas também.
