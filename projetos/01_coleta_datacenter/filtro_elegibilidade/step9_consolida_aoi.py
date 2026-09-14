"""Etapa 1 (coleta de data center) — sub-etapa: consolida facilities em AOIs.

Roda DEPOIS de `step8_filtra_elegibilidade.py`. Facilities do mesmo operador, a até
`config.RAIO_MESMO_AOI_M` de distância, são o mesmo campus/AOI — mesma lógica de dedup por AOI
da SV-24 do `modelo-imagens-satelite` (lá com buffer de 5 km, pensado pra área de imagem de
satélite; aqui 600 m, só pra identificar "é o mesmo campus", ver `config.py`).

Exemplo real: `Ascenty - Hortolandia HTL2/3/4/5` são 4 facilities do scraping, mas 1 AOI só —
o mesmo campus. Consolidar isso é o que reduz as facilities elegíveis (step8) pra um número menor
de AOIs (áreas de estudo).

**`ano_inicio_obra` por AOI**, nesta ordem de prioridade:
1. Se existe pesquisa em `config.csv_pesquisa_aoi` (operador+cidade) — usa o `ano_construcao_min`
   pesquisado, com `metodo`/`confianca`/`fonte_url` documentados.
2. Senão, **projeta**: `ano_operacional_min do AOI - config.ANOS_PROJECAO_INICIO_OBRA` — nunca
   fica em branco, mas fica marcado `metodo=projecao` pra quem for usar saber que não é pesquisa.

Porte (`mw_construido`, `whitespace_construido_m`) é somado entre os facilities do mesmo AOI —
representa o porte total do campus, não de 1 prédio.

Saída: `dados/silver/datacenter_filtrado.csv` — o artefato final desta sub-etapa (1 linha por
AOI), separador `;`.

Uso:
    cd projetos/01_coleta_datacenter/filtro_elegibilidade
    python step9_consolida_aoi.py
"""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import SETTINGS
import config


def _normaliza(texto: str) -> str:
    """minusculo, sem acento, sem espaço nas pontas — pra casar operador/cidade de forma robusta
    entre datacenter_filtrado_facilities.csv e aoi_construcao_pesquisada.csv."""
    texto = str(texto).strip().lower()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return texto


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def _agrupa_por_aoi(df: pd.DataFrame) -> pd.Series:
    """Union-find: facilities do mesmo operador (normalizado) a <= RAIO_MESMO_AOI_M viram 1 grupo."""
    n = len(df)
    pai = list(range(n))

    def encontra(x: int) -> int:
        while pai[x] != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x

    def une(x: int, y: int) -> None:
        rx, ry = encontra(x), encontra(y)
        if rx != ry:
            pai[rx] = ry

    op_norm = df["operadora"].map(_normaliza)
    for i in range(n):
        for j in range(i + 1, n):
            if op_norm.iloc[i] != op_norm.iloc[j]:
                continue
            d = _haversine_m(
                df.iloc[i]["latitude"], df.iloc[i]["longitude"],
                df.iloc[j]["latitude"], df.iloc[j]["longitude"],
            )
            if d <= config.RAIO_MESMO_AOI_M:
                une(i, j)

    return pd.Series([encontra(i) for i in range(n)], index=df.index)


def _carrega_pesquisa() -> dict[tuple[str, str], dict]:
    if not SETTINGS.csv_pesquisa_aoi.exists():
        return {}
    pesq = pd.read_csv(SETTINGS.csv_pesquisa_aoi, sep=";", encoding="utf-8-sig")
    resultado = {}
    for _, row in pesq.iterrows():
        chave = (_normaliza(row["operadora"]), _normaliza(row["cidade"]))
        resultado[chave] = {
            "ano_construcao_min": int(row["ano_construcao_min"]),
            "metodo": row["metodo"],
            "confianca": row["confianca"],
            "fonte_url": row.get("fonte_url", ""),
        }
    return resultado


def consolida(df: pd.DataFrame, pesquisa: dict[tuple[str, str], dict]) -> pd.DataFrame:
    df = df.copy()
    df["aoi_grupo"] = _agrupa_por_aoi(df)

    linhas = []
    for _, g in df.groupby("aoi_grupo"):
        operadora = g["operadora"].iloc[0]
        cidade = g["cidade"].iloc[0]
        chave = (_normaliza(operadora), _normaliza(cidade))
        facilities = sorted(g["nome_datacenter"].tolist())
        ano_op_min = int(g["ano_operacional"].min())
        ano_op_max = int(g["ano_operacional"].max())

        pesq = pesquisa.get(chave)
        if pesq is not None:
            ano_inicio_obra = pesq["ano_construcao_min"]
            metodo = pesq["metodo"]
            confianca = pesq["confianca"]
            fonte = pesq["fonte_url"]
        else:
            ano_inicio_obra = ano_op_min - config.ANOS_PROJECAO_INICIO_OBRA
            metodo = "projecao"
            confianca = "baixa"
            fonte = f"projetado: ano_operacional_min ({ano_op_min}) - {config.ANOS_PROJECAO_INICIO_OBRA}"

        aoi_id = f"{_normaliza(operadora).replace(' ', '-')}-{_normaliza(cidade).replace(' ', '-')}"

        linhas.append({
            "aoi_id": aoi_id,
            "operadora": operadora,
            "cidade": cidade,
            "n_facilities": len(g),
            "facilities": "; ".join(facilities),
            "latitude": g["latitude"].mean(),
            "longitude": g["longitude"].mean(),
            "mw_construido_total": g["mw_construido"].sum(min_count=1),
            "whitespace_construido_m_total": g["whitespace_construido_m"].sum(min_count=1),
            "ano_operacional_min": ano_op_min,
            "ano_operacional_max": ano_op_max,
            "ano_inicio_obra": ano_inicio_obra,
            "metodo_ano_inicio_obra": metodo,
            "confianca_ano_inicio_obra": confianca,
            "fonte_ano_inicio_obra": fonte,
        })

    return pd.DataFrame(linhas).sort_values("aoi_id").reset_index(drop=True)


def main() -> None:
    if not SETTINGS.csv_facilities.exists():
        raise SystemExit(
            f"{SETTINGS.csv_facilities} não existe — rode step8_filtra_elegibilidade.py antes "
            f"desta sub-etapa."
        )

    df = pd.read_csv(SETTINGS.csv_facilities, sep=";", encoding="utf-8-sig")
    print(f"{len(df)} facilities elegíveis lidas de {SETTINGS.csv_facilities.name}")

    pesquisa = _carrega_pesquisa()
    print(f"{len(pesquisa)} AOIs com pesquisa real em {SETTINGS.csv_pesquisa_aoi.name}")

    aois = consolida(df, pesquisa)

    n_pesquisado = (aois["metodo_ano_inicio_obra"] != "projecao").sum()
    n_projetado = (aois["metodo_ano_inicio_obra"] == "projecao").sum()
    print(f"\n{len(df)} facilities -> {len(aois)} AOIs "
          f"({n_pesquisado} com ano_inicio_obra pesquisado, {n_projetado} projetado)")

    SETTINGS.csv_final.parent.mkdir(parents=True, exist_ok=True)
    aois.to_csv(SETTINGS.csv_final, sep=";", index=False, encoding="utf-8")
    print(f"Salvo em {SETTINGS.csv_final}")


if __name__ == "__main__":
    main()
