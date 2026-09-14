"""Etapa 1 (coleta de data center) — sub-etapa: corrige endereço via reverse geocoding.

Roda DEPOIS de `run_pipeline.py` (etapa 1 principal), que gera
`dados/bronze/datacentermap/datacentermap_datacenters.csv`. Usa `latitude`/`longitude` — sempre
preenchidas, vêm do próprio datacentermap.com — para consultar a Google Geocoding API e obter
endereço, município, estado, país e CEP.

**Por que isso é necessário:** os campos `endereco`, `cidade`, `estado`, `pais`, `cep` que já vêm
do scraping são texto livre digitado por quem cadastrou o data center no datacentermap.com —
abreviações, espaço sobrando, UF vazia (várias linhas têm `cidade` mas não `estado`). Downstream
(Modelo 2 casa `município`/`uf` com o IBGE) precisa de um valor padronizado.

**Estratégia (complementar x sempre atualizar) — diferente por campo:**
- `municipio` (`cidade`) e `estado`: **sempre atualizados** com o valor da Geocoding API quando
  ela responde `OK`, mesmo que o scraping já tivesse um valor — é o par que o Modelo 2 usa pra
  casar com o IBGE, então vale mais confiar sempre no geocoding do que no que foi digitado.
- `endereco`, `cep`, `pais`: só **complementados** — o valor do scraping é mantido sempre que já
  existe; a Geocoding API só entra pra preencher o que está vazio. (CEP e país seguem o mesmo
  raciocínio do endereço por não terem um "valor de referência downstream" como município/UF —
  ajustar se quiser tratamento diferente pra algum desses três.)

**Limpeza aplicada:**
- trim de espaço em branco de toda coluna de texto (ex.: `"R. da Independencia, 632 "` — reparar
  o espaço sobrando no fim);
- linhas sem `latitude`/`longitude` não chamam a API (não dá pra geocodificar sem coordenada) —
  ficam com `status_geocode = "LAT_LON_AUSENTE"`, não são descartadas nem alteradas;
- `status_geocode` é mantido por linha (`OK`, `ZERO_RESULTS`, `LAT_LON_AUSENTE`, `ERRO_REDE: ...`,
  `ERRO_API: ...`) — falha de geocoding não descarta a linha, só deixa os campos como já
  estavam no scraping.

Saída: `dados/silver/datacentermap_enderecos_corrigidos.csv` (mesmo separador `;` do bronze,
mesmos nomes de coluna do bronze — `endereco`/`cidade`/`estado`/`pais`/`cep` — só que
complementados/atualizados, mais o `status_geocode`).

Precisa de `GOOGLE_MAPS_API_KEY` no `.env` da raiz (Geocoding API habilitada + faturamento ativo).

Uso:
    cd projetos/01_coleta_datacenter/correcao_endereco
    pip install -r requirements.txt
    python step7_corrige_endereco.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import SETTINGS

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
MAX_TENTATIVAS = 5
PAUSA_ENTRE_CHAMADAS_SEG = 0.1

# Campos sempre atualizados pelo geocoding (nome da coluna final -> nome da coluna geocodificada).
CAMPOS_SEMPRE_ATUALIZA = {"cidade": "municipio_geocode", "estado": "estado_geocode"}
# Campos só complementados onde o scraping já não tem valor.
CAMPOS_COMPLEMENTA = {"endereco": "endereco_geocode", "cep": "cep_geocode", "pais": "pais_geocode"}


def _extrai_componente(components: list[dict], tipo: str, campo: str = "long_name") -> str | None:
    for c in components:
        if tipo in c.get("types", []):
            return c.get(campo)
    return None


def geocodifica(lat: float, lon: float, api_key: str) -> dict:
    """Consulta a Geocoding API para 1 par lat/lon. Nunca lança — sempre devolve um dict com
    status_geocode, mesmo em falha (rede, API, sem resultado)."""
    params = {"latlng": f"{lat},{lon}", "key": api_key}
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            resp = requests.get(GEOCODE_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            if tentativa == MAX_TENTATIVAS:
                return {"status_geocode": f"ERRO_REDE: {exc}"}
            time.sleep(2**tentativa)
            continue

        status = data.get("status")
        if status == "ZERO_RESULTS":
            return {"status_geocode": "ZERO_RESULTS"}
        if status != "OK":
            if tentativa == MAX_TENTATIVAS:
                return {"status_geocode": f"ERRO_API: {status}"}
            time.sleep(2**tentativa)
            continue

        resultado = data["results"][0]
        components = resultado.get("address_components", [])
        municipio = _extrai_componente(components, "administrative_area_level_2") or _extrai_componente(
            components, "locality"
        )
        return {
            "endereco_geocode": resultado.get("formatted_address"),
            "municipio_geocode": municipio,
            "estado_geocode": _extrai_componente(components, "administrative_area_level_1", "short_name"),
            "pais_geocode": _extrai_componente(components, "country"),
            "cep_geocode": _extrai_componente(components, "postal_code"),
            "status_geocode": "OK",
        }
    return {"status_geocode": "ERRO_DESCONHECIDO"}


def _vazio(serie: pd.Series) -> pd.Series:
    return serie.isna() | (serie.astype(str).str.strip() == "")


def main() -> None:
    if not SETTINGS.csv_bronze.exists():
        raise SystemExit(
            f"{SETTINGS.csv_bronze} não existe — rode a coleta (run_pipeline.py, etapa 1) antes "
            f"desta sub-etapa."
        )

    df = pd.read_csv(SETTINGS.csv_bronze, sep=";", encoding="utf-8-sig")
    print(f"{len(df)} data centers lidos de {SETTINGS.csv_bronze.name}")

    # Limpeza: tira espaço em branco sobrando de toda coluna de texto.
    colunas_texto = df.select_dtypes(include="object").columns
    df[colunas_texto] = df[colunas_texto].apply(lambda s: s.str.strip())

    tem_coordenada = df["latitude"].notna() & df["longitude"].notna()
    n_sem_coordenada = int((~tem_coordenada).sum())
    if n_sem_coordenada:
        print(
            f"AVISO: {n_sem_coordenada} linha(s) sem lat/lon — status_geocode=LAT_LON_AUSENTE, "
            f"sem chamar a API pra essas (campos ficam como vieram do scraping)."
        )

    api_key = SETTINGS.google_maps_api_key
    resultados = []
    for i, row in df.iterrows():
        if not tem_coordenada[i]:
            resultados.append({"status_geocode": "LAT_LON_AUSENTE"})
            continue
        resultados.append(geocodifica(row["latitude"], row["longitude"], api_key))
        time.sleep(PAUSA_ENTRE_CHAMADAS_SEG)
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{len(df)} geocodificados...")

    geocode_df = pd.DataFrame(resultados)
    df = pd.concat([df.reset_index(drop=True), geocode_df], axis=1)

    n_ok = int((df["status_geocode"] == "OK").sum())
    print(f"Geocoding OK em {n_ok}/{len(df)} linhas ({100 * n_ok / len(df):.1f}%).")
    tem_ok = df["status_geocode"] == "OK"

    # Município e estado: SEMPRE atualiza com o valor do geocoding, onde ele respondeu OK —
    # mesmo que o scraping já tivesse um valor preenchido.
    for coluna_final, coluna_geocode in CAMPOS_SEMPRE_ATUALIZA.items():
        df.loc[tem_ok, coluna_final] = df.loc[tem_ok, coluna_geocode]

    # Endereço, CEP e país: só COMPLEMENTA onde o scraping deixou vazio — nunca sobrescreve o que
    # já veio preenchido.
    for coluna_final, coluna_geocode in CAMPOS_COMPLEMENTA.items():
        precisa_complementar = _vazio(df[coluna_final]) & tem_ok
        df.loc[precisa_complementar, coluna_final] = df.loc[precisa_complementar, coluna_geocode]

    # Descarta as colunas auxiliares (*_geocode) — já foram absorvidas nas colunas finais acima.
    df = df.drop(columns=list(CAMPOS_SEMPRE_ATUALIZA.values()) + list(CAMPOS_COMPLEMENTA.values()))

    SETTINGS.csv_silver.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(SETTINGS.csv_silver, sep=";", index=False, encoding="utf-8-sig")
    print(f"\nSalvo em {SETTINGS.csv_silver}")


if __name__ == "__main__":
    main()
