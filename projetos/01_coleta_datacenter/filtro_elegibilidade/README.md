# filtro_elegibilidade — sub-etapa 1 (pós-coleta, encadeada depois de `correcao_endereco/`)

Roda **depois** de `correcao_endereco/` — que por sua vez roda depois de `run_pipeline.py`:

```
run_pipeline.py            -> dados/bronze/datacentermap/datacentermap_datacenters.csv
correcao_endereco/         -> dados/silver/datacentermap_enderecos_corrigidos.csv
filtro_elegibilidade/ (este)  -> dados/silver/datacenter_filtrado.csv
```

Pega o CSV já com endereço/município/estado padronizados pela Geocoding API e filtra só os data
centers que servem pro estudo de impacto.

## Critério de elegibilidade

Um data center entra no estudo se:

- **`status == 1`** — está ativo (não descontinuado/planejado).
- **`stage == 2`** — já foi construído (não é só projeto anunciado).
- **`tipo_listagem == 'Facility'`** — exclui listagens de "Campus" e "Multi-Tenant Building"
  (que agregam vários facilities e distorceriam a unidade de observação do estudo).
- **`ano_operacional`** entre **2018 e 2024** (exclusive nas pontas — ver
  `config.ANO_OPERACIONAL_MIN`/`MAX`; linhas sem `ano_operacional` preenchido também caem fora,
  já que `NaN` nunca satisfaz uma comparação `>`/`<`).

O motivo da janela de anos: a análise estatística (`projetos/09_analise_estatistica_impacto/`)
mede o efeito numa janela móvel ao redor do ano de abertura (ano-3 até ano+2). Um data center que
abriu antes de 2018 ou depois de 2024 não deixaria sobrar anos suficientes de série de satélite
dos dois lados da abertura.

## Como rodar

```bash
cd projetos/01_coleta_datacenter/filtro_elegibilidade
pip install -r requirements.txt
python step8_filtra_elegibilidade.py
```

- **Entrada:** `dados/silver/datacentermap_enderecos_corrigidos.csv` (saída de `correcao_endereco/`)
- **Saída:** `dados/silver/datacenter_filtrado.csv` — colunas de identificação e porte
  (`nome_datacenter`, `endereco`, `cidade`, `latitude`, `longitude`, `tags`, `mw_construido`,
  `whitespace_construido_m`, `ano_operacional`, `tipo_construcao`). `nome_datacenter` é o
  identificador usado a partir daqui — precisa ser único entre os data centers filtrados.
  `cidade` já vem padronizada pela Geocoding API (`município`/`estado` sempre atualizados, ver
  README de `correcao_endereco/`).

## Quem consome essa saída

- `modelos/modelo_2_grupo_controle/` — pareia cada data center filtrado (por `nome_datacenter`)
  com um grupo de controle.
- `projetos/02_extracao_imagem/` — usa `nome_datacenter`/`latitude`/`longitude` como lista de
  pontos a extrair do Google Earth Engine.

## Origem

Readaptação de `data-extraction/transform/filtra_datacenter/` — mesma lógica de filtro (critérios
e colunas finais idênticos). Duas diferenças da versão original: a entrada é
`dados/silver/datacentermap_enderecos_corrigidos.csv` (não `data/raw/outputs_extraction/` do
`data-extraction`), e ela vem **depois** de `correcao_endereco/` — no repositório original não
existia essa etapa de correção, então o filtro partia direto do bronze.

## Por que ainda sem `estado` no CSV final

`COLUNAS_FINAIS` (`config.py`) não inclui `estado`, mesmo ele já vindo confiável de
`correcao_endereco/` — mantém o schema idêntico ao filtro original pra não quebrar quem já
consome `datacenter_filtrado.csv` (ex.: Modelo 2). Se for útil ter `estado` no CSV final agora
que ele é padronizado, é só adicionar `"estado"` em `COLUNAS_FINAIS`.
