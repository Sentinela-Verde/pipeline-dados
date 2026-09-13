"""Step 1 — encontra, para cada município brasileiro, os municípios mais parecidos
socioeconomicamente (candidatos a grupo de controle).

Usa KNN (distância euclidiana sobre features padronizadas em Z-Score) dentro de cada
região do país (ver `config.MODO_REGIAO`), a partir do perfil médio 2016-2021 de
população, PIB per capita e vocação econômica (`config.FEATURES_CIDADE`).

Uso:
    python step1_cidades_similares.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler


def adicionar_cidades_similares(df_input, features, modo_regiao="mesma", n_similares=3):
    """Adiciona colunas com os IDs, nomes e % de similaridade dos municípios mais próximos.

    Novas colunas geradas para cada similar (i de 1 a n_similares):
      - id_municipio_similar_{i}
      - municipio_similar_{i}
      - percentual_similaridade_{i}
    """
    df_resultado = df_input.copy()

    for i in range(1, n_similares + 1):
        df_resultado[f"id_municipio_similar_{i}"] = None
        df_resultado[f"municipio_similar_{i}"] = None
        df_resultado[f"percentual_similaridade_{i}"] = np.nan

    # Grupos de execução: por região, ou Brasil inteiro de uma vez.
    if modo_regiao == "mesma":
        grupos = df_resultado.groupby("regiao")
    else:
        grupos = [("brasil", df_resultado)]

    for _, grupo_df in grupos:
        if len(grupo_df) <= 1:
            continue

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(grupo_df[features])

        k = min(len(grupo_df), n_similares + 1)
        knn = NearestNeighbors(n_neighbors=k, metric="euclidean")
        knn.fit(X_scaled)
        distances, indices = knn.kneighbors(X_scaled)

        for idx_local, (dists, idxs) in enumerate(zip(distances, indices)):
            idx_global = grupo_df.index[idx_local]

            # Ignora o índice 0 (a própria cidade).
            sim_count = 1
            for d, idx_vizinho in zip(dists[1:], idxs[1:]):
                id_sim = grupo_df.iloc[idx_vizinho]["id_municipio"]
                cidade_sim = grupo_df.iloc[idx_vizinho]["nome_municipio"]
                uf_sim = grupo_df.iloc[idx_vizinho]["sigla_uf"]
                nome_formatado = f"{cidade_sim} ({uf_sim})"

                # Percentual de similaridade = exponencial da distância Z-Score.
                sim_pct = round(np.exp(-d / 2.0) * 100, 2)

                df_resultado.at[idx_global, f"id_municipio_similar_{sim_count}"] = int(id_sim)
                df_resultado.at[idx_global, f"municipio_similar_{sim_count}"] = nome_formatado
                df_resultado.at[idx_global, f"percentual_similaridade_{sim_count}"] = sim_pct
                sim_count += 1

    return df_resultado


def main():
    df = pd.read_csv(config.IBGE_CSV)
    print(f"Lidos {len(df)} registros (município x ano) de {config.IBGE_CSV}")

    df_intervalo = df[df["ano"].isin(config.ANOS_ANALISE)].copy()
    df_agrupado = (
        df_intervalo
        .groupby(["id_municipio", "nome_municipio", "sigla_uf", "regiao"])[config.FEATURES_CIDADE]
        .mean()
        .reset_index()
    )
    print(f"{len(df_agrupado)} municípios, perfil médio {min(config.ANOS_ANALISE)}-{max(config.ANOS_ANALISE)}")

    df_final = adicionar_cidades_similares(
        df_agrupado, config.FEATURES_CIDADE,
        modo_regiao=config.MODO_REGIAO, n_similares=config.N_SIMILARES,
    )

    df_final.to_csv(config.MUNICIPIOS_SIMILARES_CSV, index=False, encoding="utf-8-sig")
    print(f"Salvo em {config.MUNICIPIOS_SIMILARES_CSV}")


if __name__ == "__main__":
    main()
