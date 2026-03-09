from vault_utils import get_secrets
import logging

logger = logging.getLogger(__name__)

def get_aws_credentials(group: str):
    """
    Recupera le chiavi AWS da Vault in base al gruppo dell'utente.
    ######################TODO####################: il path su Vault sarà: infrastructure/aws/{group}
    """
    try:
        vault_path = f"infrastructure/aws/{group}"
        secrets = get_secrets(vault_path)
        
        if not secrets:
            logger.warning(f"Nessun segreto trovato per il gruppo {group}, provo il default")
            secrets = get_secrets("infrastructure/aws/default")

        return {
            "access": secrets.get("access_key"),
            "secret": secrets.get("secret_key")
        }

    except Exception as e:
        logger.error(f"Errore recupero credenziali AWS da Vault: {e}")
        return None
