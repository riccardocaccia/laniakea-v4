from vault_utils import get_secrets

segreti = get_secrets("SECRET/test") 

if segreti:
    valore = segreti.get('chiave-prova')
    print(f"Successo! Valore letto: {valore}")
else:
    print("Ancora niente, controlla il path.")
