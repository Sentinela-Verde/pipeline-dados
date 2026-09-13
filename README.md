# Sugestão de estrutura de pastas — dados, modelos e projetos

Proposta v1 para o time de arquitetura, derivada direto do
[diagrama de pipeline](diagrama.html) já revisado. Hoje o pipeline
está espalhado em **3 repositórios** (`data-extraction`, `modelo-imagens-satelite` e o protótipo
abandonado `datacenter-extracao-modelos`), cada um com sua própria convenção de pastas — esta
proposta organiza tudo sob uma estrutura única, agrupando por **dados / modelos / projetos**, do
jeito que o time pediu.

> Isto é ponto de partida pra discussão, não decisão fechada — em particular, os 5 pontos
> marcados como "⚠ decisão em aberto" abaixo precisam de um dono antes de qualquer migração.

## Árvore proposta

```
sentinela_verde/
│
├── dados/                                  # data lake — 1 convenção única (ver decisão 1)
│   ├── bronze/                             # bruto, exatamente como veio da fonte
│   │   ├── datacentermap/                  # scraping (JSON cru, cache incremental)
│   │   ├── imagens_satelite/
│   │   │   ├── landsat/
│   │   │   └── sentinel2/
│   │   ├── labels/
│   │   │   ├── mapbiomas/
│   │   │   └── worldcover/
│   │   ├── ibge/
│   │   └── socioeconomico_us/              # equivalente ao IBGE, para grupo controle nos EUA (⚠ fonte a definir)
│   │
│   ├── silver/                             # tratado / intermediário
│   │   ├── features/                       # bandas + 7 índices, por sensor x site x ano
│   │   ├── expansao_amostra/               # série no raio menor + calibrador de obra (etapa 9)
│   │   └── grupo_controle/                 # 6 candidatos + comparação estatística (etapa 6/6a) + escolha final
│   │
│   ├── gold/                               # pronto pra modelar / analisar
│   │   ├── dataset_classificacao.parquet   # dataset amostrado que alimenta o treino (5a)
│   │   ├── consolidado_impacto_modelo.csv  # ⚠ hoje montado manualmente — etapa 7 do diagrama
│   │   └── efeito_liquido/                 # saídas do step1: curvas, event study, CSVs
│   │
│   ├── labels_manual/                      # 211 polígonos humanos — é INSUMO versionado, não saída
│   └── manifests/                          # proveniência (sha256, parâmetros) — sempre commitado
│
├── modelos/
│   ├── modelo_1_classificacao_imagem/
│   │   ├── treino/                         # sentinela.train — roda 1x, gera o artefato (etapa 5a)
│   │   ├── inferencia/                     # sentinela.predict — reaplica (etapas 5b e 6b)
│   │   ├── config/                         # classes.yml, params.yml, sites.geojson
│   │   └── artefatos/                      # *.joblib + *.sha256 (binário — ver decisão 2)
│   │
│   └── modelo_2_grupo_controle/
│       ├── selecao_candidatos/             # KNN cidade similar (BR ou US) + 6 pontos candidatos
│       ├── comparacao_estatistica/         # chama a inferência do modelo 1 (dependência cruzada,
│       │                                   # ver nota abaixo) + compara nível/tendência pré-obra
│       └── artefatos/
│
├── projetos/                               # 1 pasta por etapa do diagrama, numeradas na mesma ordem
│   ├── 01_coleta_datacenter/
│   ├── 02_extracao_imagem/
│   ├── 03_extracao_labels/
│   ├── 04_indices_espectrais/
│   ├── 05_extracao_lst/
│   ├── 06_extracao_socioeconomico/         # ibge/ (Brasil) + socioeconomico_us/ (⚠ fonte a definir)
│   ├── 07_reiteracao_expansao_amostra/     # + candidatos do scraping, joblib em raio menor, calibrador de obra
│   ├── 08_consolidacao/                    # ⚠ não existe hoje — ver decisão 3
│   └── 09_analise_estatistica_impacto/     # step1: event study, placebo, DiD, curva efeito líquido
│
├── docs/
│   ├── decisoes/                           # ADRs (ex.: status de propostas como Dynamic World)
│   ├── tarefas/                            # 1 tarefa por arquivo
│   └── guia_estrutura_dados.md
│
├── apresentacao/                           # material pra banca/stakeholders (já existe hoje)
│
└── proximos_passos/                        # backlog isolado, fora do pipeline ativo
    ├── energia_aneel_mme/                  # já tem coleta pronta, não conectada
    ├── agua_snis/                          # já tem coleta pronta, não conectada
    └── ruido/                              # sem fonte de dado ainda
```

## De-para com o que existe hoje

| Repositório atual | Pasta/arquivo atual | Vai para |
|---|---|---|
| `data-extraction` | `extract/scraping_datacentermap/` | `projetos/01_coleta_datacenter/` |
| `modelo-imagens-satelite` | `src/sentinela/gee/{auth,harmonizacao,sentinel2,landsat}.py` | `projetos/02_extracao_imagem/` — ✅ **migrado** |
| `data-extraction` | `extract/imagens_satelite/{landsat,sentinel2}/` | ~~`projetos/02_extracao_imagem/`~~ — não migra, ver decisão 6 |
| `data-extraction` | `extract/bigquery_ibge/` | `projetos/06_extracao_socioeconomico/ibge/` |
| — | *(não existe ainda)* | `projetos/06_extracao_socioeconomico/socioeconomico_us/` — precisa de fonte equivalente ao IBGE pros EUA |
| `data-extraction` | `modeling/modelo_grupo_controle/` | `modelos/modelo_2_grupo_controle/selecao_candidatos/` |
| — | *(não existe ainda)* | `modelos/modelo_2_grupo_controle/comparacao_estatistica/` — reaplica o `.joblib` do modelo 1 nos 6 candidatos e compara nível/tendência com o data center |
| `data-extraction` | `modeling/modelo_impacto/step1_*.py` | `projetos/09_analise_estatistica_impacto/` |
| `data-extraction` | `data/{bronze,silver,gold}/` | `dados/{bronze,silver,gold}/` (já usa a convenção proposta) |
| `modelo-imagens-satelite` | `src/sentinela/dataset.py`, `train.py` | `modelos/modelo_1_classificacao_imagem/treino/` |
| `modelo-imagens-satelite` | `src/sentinela/predict.py` | `modelos/modelo_1_classificacao_imagem/inferencia/` |
| `modelo-imagens-satelite` | `config/`, `models/*.joblib` | `modelos/modelo_1_classificacao_imagem/{config,artefatos}/` |
| `modelo-imagens-satelite` | `data/{raw,interim,processed}/` | `dados/{bronze,silver,gold}/` (precisa migrar convenção) |
| `modelo-imagens-satelite` | `data/labels_manual/`, `data/manifests/` | `dados/{labels_manual,manifests}/` (sem mudança) |
| `modelo-imagens-satelite` | `scripts/nucleo_datacenter_por_ano.py`, `datar_obra_por_serie.py` | `projetos/07_reiteracao_expansao_amostra/` — ⚠ hoje esses scripts só reaproveitam classificação já feita (raio 500m sobre os 15 sites); o fluxo alvo (rodar o `.joblib` direto num raio menor para pontos *novos* do scraping) precisa de um caminho de inferência que ainda não existe |
| `modelo-imagens-satelite` | `docs/decisoes/`, `docs/tarefas/` | `docs/{decisoes,tarefas}/` (sem mudança) |
| `data-extraction` | `extract/aneel_energia_municipio/`, `bigquery_mme_energia_uf/`, `bigquery_snis_agua/` | `proximos_passos/{energia_aneel_mme,agua_snis}/` |
| `datacenter-extracao-modelos` | (protótipo abandonado, working tree já apagado) | não migra — decidir se arquiva o repo ou apaga de vez |

## Decisões em aberto (o time de arquitetura precisa bater o martelo)

### 1 · Uma convenção única de data lake: `bronze/silver/gold` ou `raw/interim/processed`?

Hoje os dois nomes convivem: `data-extraction` usa bronze/silver/gold (linguagem clássica de
engenharia de dados); `modelo-imagens-satelite` usa raw/interim/processed (convenção comum em
projetos de ML, tipo cookiecutter-data-science). Nenhum dos dois está errado — mas ter os dois no
mesmo pipeline obriga quem lê o código a lembrar qual repo usa qual nome. **Proposta**: padronizar
em `bronze/silver/gold`, porque já é o nome usado na camada final (a que o time de negócio/banca
mais vê, em `modeling/modelo_impacto`) — mas a decisão final é do time.

### 2 · Onde ficam os artefatos binários (`.joblib`, `.tif`, `.parquet`)?

Hoje são gitignored nos dois repos (por bom motivo — são pesados). Numa estrutura única, vale
decidir: ficam fora do controle de versão mesmo (com um manifest de proveniência apontando pra
onde buscar, como já é feito hoje), ou passam a usar algo como Git LFS / bucket S3 versionado? Isso
importa principalmente pro artefato do Modelo 1 (`rf_{tag}.joblib`) — é o "produto" mais crítico de
reproduzir.

### 3 · Quem escreve o `08_consolidacao/`?

Esta é a maior lacuna do pipeline hoje (marcada em âmbar, como etapa manual, no diagrama): não existe
nenhum script que junte classificação (tratamento + controle) + LST + IBGE num painel único — é
feito manualmente. Virar código aqui é o que fecha o pipeline ponta-a-ponta e também é pré-requisito
pra rodar a expansão da amostra (etapa 9) de forma automática, não pontual.

### 4 · Modelo 2 agora depende do Modelo 1 — isso muda a ordem de deploy/versionamento

Com a comparação estatística dos 6 candidatos (etapa 6a do diagrama) e a expansão automática da
amostra (etapa 9), `modelo_2_grupo_controle/` e `projetos/07_reiteracao_expansao_amostra/` passam a
**chamar o `.joblib` do Modelo 1** diretamente — não são mais dois modelos independentes que só se
encontram no painel consolidado. Isso tem duas implicações pra arquitetura: (1) uma mudança no
Modelo 1 (novo treino, novo `tag`) pode invalidar resultados do Modelo 2 já gerados, então vale
registrar no manifest do Modelo 2 **qual `sha256` do `.joblib`** foi usado; (2) o pacote/serviço que
expõe a inferência do Modelo 1 precisa ser importável tanto por quem roda a classificação direta
(etapas 5b/6b) quanto por quem roda a seleção de controle (6a) e a expansão (9) — ou seja, a
inferência não pode ficar "presa" dentro do projeto do Modelo 1 sem uma forma de reuso.

### 5 · Fonte de dado socioeconômico dos EUA ainda não existe

`socioeconomico_us/` está na árvore como placeholder — nenhuma extração equivalente ao IBGE para
municípios/condados americanos foi encontrada no código hoje. Antes de implementar
`modelos/modelo_2_grupo_controle/` para sites nos EUA, alguém precisa decidir a fonte (Census
Bureau ACS? BLS? outra?) — isso também é pré-requisito da expansão internacional mencionada no
ADR-006 do `modelo-imagens-satelite` (hoje proposta, não aprovada).

### 6 · Qual extração de imagem é a boa — e o que fazer com a outra ✅ decidido

Existiam **duas** implementações da etapa 2, e o de-para original apontava para a errada.
`data-extraction/extract/imagens_satelite/` puxa Sentinel-2 sem harmonização multissensor, trata
Landsat em scripts avulsos duplicados (`extraction_landsat.py` + `_300m.py`, três conversores
tif→jpg) e não tem teste nenhum. `modelo-imagens-satelite/src/sentinela/gee/` é o que o diagrama
descreve: Landsat 30 m e Sentinel-2 10 m harmonizados na **mesma grade** (origem determinística,
a de 10 m é refinamento exato da de 30 m), com manifest de proveniência por arquivo.

Migrada a segunda. Falta decidir o destino da primeira: ela ainda é o código que gerou parte do
que está em `data-extraction/data/raw/` — arquivar o repo ou só marcar a pasta como morta?

### 7 · Onde mora o dado pesado ⚠ parcialmente resolvido

A decisão 2 (artefatos binários) continua aberta pro `.joblib`, mas para imagem já tem resposta
em produção: **`.tif` vive só no S3**, no bucket bronze
`plataforma-lakehouse-bronze-149465616406-us-east-1-an`, sob
`raw/imagens_satelite/{sensor}/site_id=<id>/ano=<ano>/<ano>.tif` (particionamento Hive, pra Glue/
Athena enxergarem as partições). O **manifest é leve e fica versionado** em `dados/manifests/`,
além de espelhado no S3 — é ele que liga o commit ao arquivo remoto, via `sha256`.

Regra geral que saiu daqui, e que vale pras próximas etapas: *output leve vai pro git **e** pro
S3; output pesado vai só pro S3.*

### 8 · O WorldCover saiu do pipeline ✅ decidido

O ESA WorldCover entrou no desenho como **verificação cruzada** do MapBiomas: só em 2021 (único
ano de sobreposição real), gerando um raster de concordância que a etapa de dataset usava para
ponderar amostra (`peso_label = 1/(1+distancia_safra) × (1,0 se concorda, senão 0,5)`).

Na migração da etapa 3 descobrimos que ele **já estava inerte**. O bloco que gera a concordância é
guardado por `if fonte_principal != "dynamic_world"` — e a fonte principal virou Dynamic World em
2026-09-11. Os números confirmam: dos 494 manifests de rótulo, só **32** têm `crosscheck`
preenchido, todos da era MapBiomas; sob o DW são zero. O DW é anual nativo, não tem safra
defasada, então nem `distancia_safra` nem crosscheck têm o que fazer — os dois fatores do peso
valem 1.

Por isso o WorldCover não foi migrado: nem o código, nem as chaves de `params.yml`, nem o remap em
`classes.yml`, nem os 32 rasters de concordância. Trazer de volta só faz sentido junto com uma
volta para o MapBiomas — e nesse caso a etapa 3 seria reexecutada de qualquer forma, regerando os
manifests. Os 32 manifests antigos ficam versionados como estão, com o campo `crosscheck`
apontando para um `.tif` que não existe neste repo: são registro do que rodou lá atrás, não
entrada de nada aqui.

## Por que separar `treino/` de `inferencia/` dentro do Modelo 1

Reflete a distinção que ajustamos no diagrama: **treino roda uma vez e é caro** (gera o `.joblib`);
**inferência é barata e reaplicada várias vezes** (tratamento, controle, e potencialmente novos
sites conforme a amostra cresce). Separar as pastas deixa claro pra quem chega no repo que rodar
`inferencia/` no dia a dia é normal, mas rodar `treino/` de novo é uma decisão consciente (novo
dataset, novo experimento) — não algo que acontece a cada execução do pipeline.
