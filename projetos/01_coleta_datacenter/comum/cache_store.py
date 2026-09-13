"""Camada de cache: cada item (uma região, ou uma aba de um datacenter) vira
um JSON pequeno em disco, com um status.

A ideia é nunca reprocessar/re-baixar o que já deu certo — só o que falhou ou
foi bloqueado é tentado de novo na próxima execução.
"""
import json
import time
from pathlib import Path
from typing import Any, Optional

STATUS_OK = "ok"
STATUS_BLOQUEADO = "bloqueado"
STATUS_ERRO = "erro"


def caminho(pasta: Path, chave: str) -> Path:
    return pasta / f"{chave}.json"


def carregar(pasta: Path, chave: str) -> Optional[dict]:
    """Lê o registro de cache de `chave`, ou None se não existe / está corrompido."""
    p = caminho(pasta, chave)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def salvar(pasta: Path, chave: str, status: str, dados: Any, tentativas: int = 1) -> None:
    registro = {
        "status": status,
        "atualizado_em": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tentativas": tentativas,
        "dados": dados,
    }
    caminho(pasta, chave).write_text(
        json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def precisa_buscar(pasta: Path, chave: str, forcar: bool = False) -> bool:
    """True se ainda não existe cache OK para essa chave (ou se `forcar=True`)."""
    if forcar:
        return True
    registro = carregar(pasta, chave)
    return registro is None or registro.get("status") != STATUS_OK
