def get_aws_credentials(group: str):
    vault_simulation = {
        "elixir-italy-dev": {"access": "ID", "secret": "SECRET_KEY"},
        "default": {"access": "DEFAULT_ID", "secret": "DEFAULT_SECRET_KEY"}
    }
    return vault_simulation.get(group, vault_simulation["default"])

....# once vault is up
