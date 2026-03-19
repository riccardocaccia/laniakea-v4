from vault_utils import get_secrets
import logging

logger = logging.getLogger(__name__)

def get_aws_credentials(group: str):
    """
    Secret AWS keys retrieving based on the group of the user.
    """
    try:
        vault_path = f"SECRET/infrastructure/aws/{group}"
        secrets = get_secrets(vault_path)
        # NOTE: only for test!!!!
        if not secrets:
            logger.warning(f"No secret for the group: {group}, TRYNG THE DEFAULT.")
            secrets = get_secrets("infrastructure/aws/default")

        return {
            "access": secrets.get("access_key"),
            "secret": secrets.get("secret_key")
        }

    except Exception as e:
        logger.error(f"Error in the process of retrieving the credentials: {e}")
        return None
