from web3 import Web3
import os
from dotenv import load_dotenv

load_dotenv()

RPC_URL = os.getenv("RPC_URL")

if not RPC_URL:
    raise RuntimeError("RPC_URL not found in .env")

web3 = Web3(Web3.HTTPProvider(RPC_URL))

if not web3.is_connected():
    raise RuntimeError("Could not connect to blockchain")

print("Blockchain connected!")
print("Chain ID:", web3.eth.chain_id)


# -----------------------------------------
# Blockchain account
# -----------------------------------------

ACCOUNT = web3.eth.accounts[0]

print("Using account:", ACCOUNT)


# -----------------------------------------
# SHA-256 fingerprint
# -----------------------------------------

fingerprint = (
    "b17c9554f64516b74e512261abaeb7ccc0c2a3e97fb45cf01a03432d4e2483aa"
)

print("Fingerprint:", fingerprint)


# -----------------------------------------
# Create transaction
# -----------------------------------------

transaction = {
    "from": ACCOUNT,
    "to": ACCOUNT,
    "value": 0,
    "data": web3.to_bytes(text=fingerprint),
    "gas": 100000,
    "gasPrice": web3.eth.gas_price,
    "nonce": web3.eth.get_transaction_count(ACCOUNT),
    "chainId": web3.eth.chain_id,
}


# -----------------------------------------
# Send transaction
# -----------------------------------------

tx_hash = web3.eth.send_transaction(transaction)

print("\n================================")
print("BLOCKCHAIN RECORD")
print("================================")
print("Transaction hash:", tx_hash.hex())
print("Fingerprint      :", fingerprint)
print("================================")


# -----------------------------------------
# Wait for confirmation
# -----------------------------------------

receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

print("\nTransaction confirmed!")
print("Block number:", receipt.blockNumber)
print("Status      :", receipt.status)