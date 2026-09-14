# filtro_elegibilidade — sub-etapa 1 (pós-coleta)

Roda **depois** de `run_pipeline.py` (a coleta principal do datacentermap.com). Pega
`dados/bronze/datacentermap/datacentermap_datacenters.csv` e filtra só os data centers que
servem pro estudo de impacto.

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

- **Entrada:** `dados/bronze/datacentermap/datacentermap_datacenters.csv`
- **Saída:** `dados/silver/datacenter_filtrado.csv` — colunas de identificação e porte
  (`nome_datacenter`, `endereco`, `cidade`, `latitude`, `longitude`, `tags`, `mw_construido`,
  `whitespace_construido_m`, `ano_operacional`, `tipo_construcao`). `nome_datacenter` é o
  identificador usado a partir daqui — precisa ser único entre os data centers filtrados.

## Quem consome essa saída

- `modelos/modelo_2_grupo_controle/` — pareia cada data center filtrado (por `nome_datacenter`)
  com um grupo de controle.
- `projetos/02_extracao_imagem/` — usa `nome_datacenter`/`latitude`/`longitude` como lista de
  pontos a extrair do Google Earth Engine.

## Origem

Readaptação de `data-extraction/transform/filtra_datacenter/` — mesma lógica de filtro (critérios
e colunas finais idênticos), só trocando a entrada pra ler direto o bronze desta estrutura
(`dados/bronze/datacentermap/datacentermap_datacenters.csv`) em vez de
`data/raw/outputs_extraction/` do `data-extraction` — ver decisão sobre `transform/` no README da
raiz.

## Nota sobre `correcao_endereco/`

Esta sub-etapa lê o `endereco`/`cidade` **crus** do scraping, não a versão padronizada por
`correcao_endereco/` (`dados/silver/datacentermap_enderecos_corrigidos.csv`) — mantém o mesmo
schema/comportamento do filtro original. Se `município`/`estado` padronizados forem necessários
downstream (ex.: Modelo 2 casando com o IBGE), vale considerar encadear esta sub-etapa depois da
`correcao_endereco/` no futuro, em vez de partir direto do bronze.
