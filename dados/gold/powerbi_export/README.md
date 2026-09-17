# dados/gold/powerbi_export/

Tabelas gold geradas por `projetos/09_analise_estatistica_impacto/export_gold_powerbi.py`, para
alimentar um dashboard Power BI com duas visões: a curva de efeito líquido (agregada, todas as
áreas) e um painel por data center (imagens ano a ano, tratamento e controle lado a lado).

Restrito aos **15 pares tratamento/controle** que hoje têm imagem e classificação completas dos
dois lados — não usa a amostra estendida de `efeito_liquido_32dc/` (essa é uma análise
exploratória à parte, ver README daquela pasta).

## Tabelas

| Arquivo | Grão | Conteúdo |
|---|---|---|
| `dim_facility.csv` | 1 linha por área (30: 15 tratamento + 15 controle) | Localização, ano de obra, tier, porte (MW), distância do par — chave `site_id`, com `par_id` ligando cada controle ao seu tratamento |
| `fact_cobertura_solo_ano.csv` | área × ano × classe | % de cada classe de cobertura do solo (formato longo, uma linha por classe) |
| `fact_imagens.csv` | área × ano × tipo (raw/classificada) | Miniatura ~150px em base64 (`data:image/jpeg;base64,...`), pronta para exibir direto no relatório com Data Category = "Image URL" |
| `fact_efeito_par_horizonte.csv` | par × horizonte × variável | Efeito líquido (`delta_tratamento − delta_controle`), grão fino — permite filtro dinâmico por horizonte no dashboard |
| `dim_significancia.csv` | 1 linha por variável | p-valor, p-valor FDR, IC95% (bootstrap) e Cohen's d — copiada de `dados/gold/efeito_liquido/consequencias_terreno_resumo.csv`, não recalculada aqui |

## Relacionamentos (para o modelo do Power BI)

- `dim_facility.site_id` ↔ `fact_cobertura_solo_ano.site_id` ↔ `fact_imagens.site_id`
- `dim_facility.par_id` ↔ `fact_efeito_par_horizonte.par_id` (agrupa tratamento + controle do
  mesmo par)
- `fact_efeito_par_horizonte.variavel` ↔ `dim_significancia.variavel`

## Lacunas conhecidas (não preenchidas com dado inventado)

- `ctrl-hostdime-joao-pessoa-p01` não tem imagem em 2019/2020 — falha real de disponibilidade de
  cena Landsat sem nuvem na região, não um bug do export.
- 3 tratamentos (`clickip-manaus`, `scala-sgigsm01`, `scala-spoapa01`) têm miniatura **raw**, mas
  não têm miniatura **classificada** — o raster classificado nunca foi gerado para esses três
  (só os números agregados chegaram ao `consolidado_impacto_modelo.csv`); os controles pareados a
  eles estão completos (raw + classificada).
- A coluna `nome` em `dim_facility` é uma formatação do `site_id` para exibição (ex.: "Ascenty
  Jundiai"), não um nome oficial verificado.

## Como regerar

```bash
cd projetos/09_analise_estatistica_impacto
python export_gold_powerbi.py
```
