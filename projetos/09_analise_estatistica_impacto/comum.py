"""Funções compartilhadas entre `step1_analise_exploratoria.py` e
`step2_estagio2_modelo_efeito.py` — cálculo de ano-base, deltas e tendência pré-obra.

Ver item 3 (`horizonte`) e item 4 (ano de referência/baseline) do
`guia_estrutura_dados_modelo_impacto.md`.
"""
import numpy as np
import pandas as pd


def calcula_baseline_map(df: pd.DataFrame, vars_alvo: list[str]) -> pd.DataFrame:
    """Acha, para cada `site_id`, o ano-base (horizonte pré-obra mais próximo de 0 —
    idealmente -1) e devolve o valor de cada variável-alvo nesse ano.

    Importante: o filtro é `ano_relativo_ao_inicio_obra < 0` (estritamente antes da obra) —
    o horizonte `0` já é fase "durante", usar `<= 0` faria o ano-base cair em cima do
    próprio horizonte 0 (zerando o efeito líquido ali por construção).

    Sites sem nenhuma linha pré-obra usam o primeiro horizonte disponível como fallback.
    """
    pre = df[df["ano_relativo_ao_inicio_obra"] < 0]
    idx_baseline = pre.groupby("site_id")["ano_relativo_ao_inicio_obra"].idxmax()

    sites_sem_pre = set(df["site_id"]) - set(pre["site_id"])
    if sites_sem_pre:
        idx_fallback = (
            df[df["site_id"].isin(sites_sem_pre)]
            .groupby("site_id")["ano_relativo_ao_inicio_obra"]
            .idxmin()
        )
        idx_baseline = pd.concat([idx_baseline, idx_fallback])

    return df.loc[idx_baseline].set_index("site_id")[vars_alvo]


def calcula_deltas(df: pd.DataFrame, vars_alvo: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Adiciona uma coluna `delta_<var>` por variável-alvo (valor da linha menos o valor no
    ano-base da área). Devolve o df com as colunas novas e o `baseline_map` usado."""
    df = df.sort_values(["site_id", "ano_relativo_ao_inicio_obra"]).copy()
    baseline_map = calcula_baseline_map(df, vars_alvo)

    for col in vars_alvo:
        df[f"delta_{col}"] = df.apply(
            lambda row: row[col] - baseline_map.loc[row["site_id"], col]
            if row["site_id"] in baseline_map.index else np.nan,
            axis=1,
        )

    return df, baseline_map


def calcula_tendencia(serie_horizontes, serie_valores) -> float:
    """Inclinação da reta ajustada (regressão linear simples) sobre os anos pré-obra
    disponíveis — indica se a região já estava mudando por conta própria antes do data
    center chegar (item 5 do guia de estrutura de dados)."""
    if len(serie_horizontes) < 2:
        return np.nan
    coef = np.polyfit(serie_horizontes, serie_valores, deg=1)
    return coef[0]
