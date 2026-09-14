"""Agrupamento de footprints do OSM em campi.

Um data center costuma aparecer no OpenStreetMap como vários polígonos — um por prédio. Para
datar a obra, a unidade que interessa é o **campus**, não o prédio: prédios do mesmo campus
compartilham o mesmo evento de implantação, e datá-los separadamente contaria o mesmo caso
várias vezes.

O agrupamento é union-find sobre os centroides, com vizinhança por célula de grade para não
comparar todos contra todos: dois polígonos caem no mesmo campus se os centroides estiverem a
menos de `raio_campus_km`. A saída é um anel por prédio, agrupados sob um `campus_id`.

Veio de `impacto_dc_28_datar_eua_dw.carregar_campi()` no `modelo-imagens-satelite`. Lá era um
detalhe interno do passo que datava pelo Dynamic World; aqui é módulo próprio, porque tanto a
datação por Landsat quanto qualquer releitura futura do footprint precisam da mesma definição
de campus — e duas definições diferentes de "o que é um campus" produziriam contagens
incompatíveis sem ninguém perceber.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


def _dist_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distância em km entre dois pares (lat, lon), haversine com R=6371 km.

    É a mesma fórmula do código de origem, de propósito: o agrupamento em campi define os
    `campus_id` que todos os CSVs desta etapa usam como chave. Trocar por outra fórmula (mesmo
    uma mais exata, como a geodésica WGS84 usada em outras partes do projeto) poderia mover um
    prédio de fronteira para outro campus e renumerar tudo, quebrando o vínculo com o que já
    foi publicado.
    """
    r = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = p2 - p1
    dl = math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def carregar_campi(
    caminho: Path, raio_campus_km: float, celula_grau: float
) -> list[dict[str, Any]]:
    """Polígonos do OSM agrupados em campi, um dicionário por campus.

    Cada campus traz `campus_id` (`us-0001`, ...), centroide, `n_predios`, `nome`/`operadora`
    herdados das tags do OSM e `aneis`: a lista de anéis fechados, em [lon, lat], pronta para
    virar um `ee.Geometry.MultiPolygon`.
    """
    if not caminho.exists():
        raise FileNotFoundError(
            f"'{caminho}' não existe — é o cache de footprints do OSM, versionado em "
            f"dados/bronze/footprints_osm/."
        )
    poligonos = json.loads(caminho.read_text(encoding="utf-8"))

    cents = []
    for p in poligonos:
        g = p["geometry"]
        cents.append((sum(n["lat"] for n in g) / len(g), sum(n["lon"] for n in g) / len(g)))

    grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, c in enumerate(cents):
        grid[(int(c[0] / celula_grau), int(c[1] / celula_grau))].append(i)

    pai = list(range(len(cents)))

    def raiz(x: int) -> int:
        while pai[x] != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x

    for (gy, gx), idxs in grid.items():
        viz: list[int] = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                viz.extend(grid.get((gy + dy, gx + dx), []))
        for i in idxs:
            for j in viz:
                if i < j and _dist_km(cents[i], cents[j]) < raio_campus_km:
                    ri, rj = raiz(i), raiz(j)
                    if ri != rj:
                        pai[rj] = ri

    grupos: dict[int, list[int]] = defaultdict(list)
    for i in range(len(cents)):
        grupos[raiz(i)].append(i)

    campi = []
    for k, (_, membros) in enumerate(sorted(grupos.items()), start=1):
        aneis = [[[n["lon"], n["lat"]] for n in poligonos[i]["geometry"]] for i in membros]
        aneis = [a if a[0] == a[-1] else a + [a[0]] for a in aneis]
        tags: dict[str, Any] = {}
        for i in membros:
            tags.update({k2: v for k2, v in poligonos[i].get("tags", {}).items() if v})
        campi.append(
            {
                "campus_id": f"us-{k:04d}",
                "lat": sum(cents[i][0] for i in membros) / len(membros),
                "lon": sum(cents[i][1] for i in membros) / len(membros),
                "n_predios": len(membros),
                "nome": tags.get("name"),
                "operadora": tags.get("operator"),
                "aneis": aneis,
            }
        )
    return campi
