"""Fonte única de verdade das classes de cobertura do solo — carrega parametros/classes.yml.

Nenhum outro módulo deve hardcodar número de classe: importe `CLASSES`, `SLUG_TO_ID`,
`ID_TO_SLUG` ou use `remap()`/`colormap()` daqui.

Adicionar uma nova fonte de remap (ex.: mapbiomas) é só editar a seção `remaps` do YAML —
este arquivo não precisa mudar.
"""

from __future__ import annotations

import numpy as np
import yaml

from config import PARAMS_DIR

_YAML_PATH = PARAMS_DIR / "classes.yml"


def _load_raw() -> dict:
    with _YAML_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


_raw = _load_raw()

CLASSES: dict[int, dict] = {int(k): v for k, v in _raw["classes"].items()}
SLUG_TO_ID: dict[str, int] = {meta["slug"]: class_id for class_id, meta in CLASSES.items()}
ID_TO_SLUG: dict[int, str] = {class_id: meta["slug"] for class_id, meta in CLASSES.items()}
REMAPS: dict[str, dict[int, int]] = {
    fonte: {int(codigo): int(classe_id) for codigo, classe_id in tabela.items()}
    for fonte, tabela in _raw["remaps"].items()
}


def remap(array: np.ndarray, fonte: str) -> np.ndarray:
    """Remapeia um array de códigos de origem (ex.: WorldCover) para nossos ids de classe.

    Código não presente na tabela de remap da fonte vira 0 (nodata) — nunca estoura exceção.
    Preserva shape e dtype do array de entrada.
    """
    if fonte not in REMAPS:
        raise KeyError(
            f"Fonte de remap '{fonte}' não existe em parametros/classes.yml (seção 'remaps'). "
            f"Fontes disponíveis: {list(REMAPS)}"
        )
    tabela = REMAPS[fonte]
    out = np.zeros_like(array)
    for codigo_origem, classe_id in tabela.items():
        out[array == codigo_origem] = classe_id
    return out


def colormap() -> dict[int, tuple[int, int, int]]:
    """id de classe -> tupla RGB (0-255), para escrever no GeoTIFF classificado (SV-14)."""
    result: dict[int, tuple[int, int, int]] = {}
    for class_id, meta in CLASSES.items():
        hexa = meta["cor_hex"].lstrip("#")
        result[class_id] = tuple(int(hexa[i : i + 2], 16) for i in (0, 2, 4))
    return result
