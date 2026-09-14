"""Step 3 — escolhe, para cada AOI, o candidato a grupo de controle mais parecido com o próprio
data center no período PRÉ-OBRA, segundo o classificador (modelo 1), não segundo proximidade
geográfica ou similaridade socioeconômica (isso já decidiu QUEM são os 12 candidatos — steps 1-2).

Critério portado de `modelo-imagens-satelite/modelo-impacto/scripts/impacto_dc_comum.py`
(`distancia_l1`/`qualidade_l1`) — a mesma distância L1 entre distribuições de classe (proporção de
vegetação densa/rala, solo exposto, área construída, água) que aquele repositório usa pra parear
tratamento x controle pelo classificador. Adaptado num ponto: lá a comparação é num ÚNICO
"ano de referência" (obra-1); aqui, como o usuário pediu uma JANELA pré-obra de 3 anos
(obra-3..obra-1, não 1 ano só), a distribuição de cada lado (AOI e cada candidato) é a MÉDIA das
proporções de classe nos 3 anos — mais robusta a um ano atípico (nuvem residual, cena ruim) do que
um único ano, ao custo de "borrar" uma mudança que só aconteceu num dos 3 anos.

Entrada:
    dados/silver/grupo_controle/percentuais_classificacao_pre_obra.csv (modelo_1, step anterior)
    dados/silver/grupo_controle/candidatos_grupo_controle_12pontos.csv (steps 1-2, mapeia
        candidato_id -> aoi_id)

Saída:
    dados/silver/grupo_controle/grupo_controle_escolhido.csv — 1 linha por AOI: o candidato
    vencedor (menor L1), sua qualidade (bom/aceitável/ruim) e os 11 outros candidatos avaliados
    pra auditoria (não descartados — mesmo princípio de SV-24/25 de nunca jogar fora a régua de
    decisão).

Uso:
    python step3_seleciona_melhor_controle.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

import numpy as np
import pandas as pd

CLASSES = ("vegetacao_densa", "vegetacao_rala", "solo_exposto_obras", "construida_urbana", "agua")
COLUNAS_PROP = [f"prop_{c}" for c in CLASSES]

PERCENTUAIS_CSV = config.GRUPO_CONTROLE_DIR / "percentuais_classificacao_pre_obra.csv"
GRUPO_CONTROLE_ESCOLHIDO_CSV = config.GRUPO_CONTROLE_DIR / "grupo_controle_escolhido.csv"


def qualidade_l1(l1: float) -> str:
    """`bom` <= 0.10 · `aceitavel` <= 0.20 · `ruim` acima — mesmos limiares de SV-29/`impacto_dc_comum.py`."""
    if l1 <= 0.10:
        return "bom"
    if l1 <= 0.20:
        return "aceitavel"
    return "ruim"


def distribuicao_media(df_percentuais: pd.DataFrame, site_id: str) -> np.ndarray | None:
    """Média das `COLUNAS_PROP` nos anos disponíveis para `site_id` — None se não há nenhum ano."""
    linhas = df_percentuais[df_percentuais["site_id"] == site_id]
    if linhas.empty:
        return None
    return linhas[COLUNAS_PROP].mean(axis=0).to_numpy()


def distancia_l1(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a - b).sum())


def main() -> None:
    if not PERCENTUAIS_CSV.exists():
        raise SystemExit(
            f"{PERCENTUAIS_CSV} não existe — rode a extração (etapa 2) + índices (etapa 4) + "
            f"classificação (modelo_1/inferencia/classifica.py --saida-csv ...) antes."
        )

    percentuais = pd.read_csv(PERCENTUAIS_CSV, sep=";", encoding="utf-8-sig")
    candidatos = pd.read_csv(config.CANDIDATOS_GRUPO_CONTROLE_CSV, sep=";", encoding="utf-8-sig")

    aois = sorted(candidatos["aoi_id"].unique())
    print(f"{len(aois)} AOIs, {candidatos['candidato_id'].nunique()} candidatos únicos")

    linhas_saida = []
    for aoi_id in aois:
        dist_aoi = distribuicao_media(percentuais, aoi_id)
        if dist_aoi is None:
            print(f"AVISO: {aoi_id} sem classificação no período pré-obra — pulando (rode a "
                  f"extração/classificação pra esse AOI antes).", file=sys.stderr)
            continue

        avaliados = []
        for _, row in candidatos[candidatos["aoi_id"] == aoi_id].drop_duplicates("candidato_id").iterrows():
            cand_id = row["candidato_id"]
            dist_cand = distribuicao_media(percentuais, cand_id)
            if dist_cand is None:
                continue
            l1 = distancia_l1(dist_aoi, dist_cand)
            avaliados.append({
                "aoi_id": aoi_id,
                "candidato_id": cand_id,
                "similar_rank": int(row["similar_rank"]),
                "municipio_similar": row["municipio_similar"],
                "ponto_latitude": row["ponto_latitude"],
                "ponto_longitude": row["ponto_longitude"],
                "l1": round(l1, 6),
                "qualidade": qualidade_l1(l1),
            })

        if not avaliados:
            print(f"AVISO: {aoi_id} — nenhum dos 12 candidatos tem classificação pré-obra ainda.",
                  file=sys.stderr)
            continue

        avaliados.sort(key=lambda a: a["l1"])
        for posicao, a in enumerate(avaliados, 1):
            a["posicao"] = posicao
            a["escolhido"] = posicao == 1
            linhas_saida.append(a)

        vencedor = avaliados[0]
        print(f"{aoi_id}: vencedor {vencedor['candidato_id']} "
              f"(L1={vencedor['l1']:.4f}, {vencedor['qualidade']}) "
              f"de {len(avaliados)} candidatos avaliados")

    df_saida = pd.DataFrame(linhas_saida)
    df_saida.to_csv(GRUPO_CONTROLE_ESCOLHIDO_CSV, sep=";", index=False, encoding="utf-8-sig")
    print(f"\nSalvo em {GRUPO_CONTROLE_ESCOLHIDO_CSV} ({len(df_saida)} linhas — "
          f"{df_saida['aoi_id'].nunique()} AOIs x até 12 candidatos avaliados cada)")


if __name__ == "__main__":
    main()
