"""Autenticação e inicialização do Google Earth Engine.

Dois modos, nesta ordem de preferência:
  a) Service account (EE_SERVICE_ACCOUNT_KEY definido) — sem browser, para lote/CI.
  b) Usuário (ee.Authenticate(), uma vez) — abre o navegador padrão do sistema.

Idempotente: chamar init_ee() mais de uma vez não reautentica.
"""

from __future__ import annotations

import truststore

# Faz o Python validar TLS usando a store de certificados do próprio Windows (via SChannel), em
# vez da checagem RFC 5280 estrita do OpenSSL embutido no Python 3.13. Sem isso, em máquinas com
# antivírus/VPN que inspeciona HTTPS, ee.Authenticate() falha com
# "CERTIFICATE_VERIFY_FAILED: Basic Constraints of CA cert not marked critical" ao trocar o código
# de autorização por um token — a mesma CA que o navegador aceita sem problema.
truststore.inject_into_ssl()

import ee

from config import SETTINGS, ConfigError

_initialized = False


def init_ee() -> None:
    global _initialized
    if _initialized:
        return

    project = SETTINGS.ee_project  # levanta ConfigError com mensagem clara se faltar

    key_path = None
    try:
        key_path = SETTINGS.ee_service_account_key
    except ConfigError:
        pass  # EE_SERVICE_ACCOUNT_KEY é opcional — cai para autenticação de usuário

    try:
        if key_path is not None and str(key_path) not in ("", ".", "None"):
            if not key_path.exists():
                raise ConfigError(
                    f"EE_SERVICE_ACCOUNT_KEY aponta para '{key_path}', que não existe. "
                    f"Confira o caminho no .env (deve ser absoluto e ficar FORA do repositório)."
                )
            credentials = ee.ServiceAccountCredentials(email=None, key_file=str(key_path))
            ee.Initialize(credentials, project=project)
        else:
            ee.Authenticate()  # no-op se já houver token válido em ~/.config/earthengine/
            ee.Initialize(project=project)
    except ee.EEException as e:
        message = str(e)
        if "not registered" in message.lower() or "not signed up" in message.lower():
            raise ConfigError(
                f"O projeto '{project}' não está registrado para usar o Earth Engine.\n"
                f"Registre em https://code.earthengine.google.com/register e escolha um caso de "
                f"uso não-comercial (acadêmico/pesquisa) para este projeto GCP. Depois rode de novo.\n"
                f"Detalhe original: {message}"
            ) from e
        raise

    _initialized = True
