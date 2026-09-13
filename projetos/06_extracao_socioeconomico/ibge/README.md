# bigquery_ibge — coleta da Base dos Dados / IBGE (BigQuery)

Extração dos indicadores socioeconômicos dos municípios brasileiros (PIB,
população, vocação econômica) via BigQuery, usando a
[Base dos Dados](https://basedosdados.org/). É uma das coletas dentro de
`data-extraction/extract/` — ver o [README da raiz](../../README.md) pra
entender como as coletas se encaixam (pasta `data/raw/` compartilhada).

## Ideia geral

A Base dos Dados já publica as tabelas tratadas do IBGE (PIB, população,
diretório de municípios) no BigQuery, então não tem scraping aqui — é uma
extração direta via SQL, usando a lib `basedosdados` (`bd.read_sql`):

- `QUERY_SOCIOECONOMICO` — PIB, população e vocação econômica (% do PIB em
  serviços/indústria/agropecuária), um município por ano, a partir de
  `config.ANO_MINIMO`.
- `QUERY_LAT_LONG` — latitude/longitude da sede municipal (não muda entre
  anos, então busca só um ano fixo em `config.ANO_LAT_LONG`).

O step junta as duas em um único CSV, um município por linha.

## Autenticação

Duas coisas diferentes, não confundir:

1. **`PROJECT_ID`** — projeto do Google Cloud usado só pra *faturamento* das
   queries no BigQuery (a Base dos Dados em si é pública e cabe na cota
   gratuita do BigQuery pra a maioria dos usos). Vem do `.env` na raiz do
   repo — ver `.env.example`. **Nunca comitar o `.env`** (já está no
   `.gitignore` da raiz).
2. **Credenciais do Google Cloud** — o `basedosdados` autentica via
   Application Default Credentials do `gcloud`, não por uma chave no
   `.env`. Se ainda não configurou localmente:

   ```bash
   gcloud auth application-default login
   ```

   (ou uma service account, se preferir — ver docs da
   [Base dos Dados](https://basedosdados.org/) / `google-cloud-bigquery`).

## Como rodar

```bash
cd data-extraction/extract/bigquery_ibge
pip install -r requirements.txt
python step0a_extract_dados_ibge.py
```

## Saída

- `../../data/raw/outputs_extraction/ibge_municipios.csv` — um município por linha, `utf-8-sig`
  (abre certo no Excel). Colunas:

  | Grupo | Colunas |
  |---|---|
  | Identificação | `nome_municipio`, `sigla_uf`, `regiao`, `id_municipio`, `ano` |
  | Demografia | `populacao` |
  | Economia | `pib`, `pib_per_capita`, `va_servicos`, `va_industria`, `va_agropecuaria`, `impostos_liquidos`, `pct_va_servicos`, `pct_va_industria`, `pct_va_agropecuaria`, `pct_impostos` |
  | Geo | `latitude`, `longitude` |

  A série vai de `config.ANO_MINIMO` (hoje `2016`) até o último ano
  disponível na Base dos Dados.
