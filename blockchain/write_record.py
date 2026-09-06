import os
from web3 import Web3
from dotenv import load_dotenv


def connect_blockchain():
    """Connects to local Ganache blockchain or custom RPC URL."""
    load_dotenv()
    rpc_url = os.getenv("RPC_URL", "http://127.0.0.1:8545")

    try:
        web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 5}))
        if not web3.is_connected():
            return None
        return web3
    except Exception:
        return None


def write_fingerprint(fingerprint):
    """
    Writes a SHA-256 fingerprint to the local Ganache blockchain.
    Returns transaction hash string if successful, or None if connection fails.
    """
    if not fingerprint:
        raise ValueError("Fingerprint cannot be empty.")

    web3 = connect_blockchain()
    if not web3:
        print("⚠️ Blockchain Notice: Local Ganache node is offline (http://127.0.0.1:8545). Skipping on-chain write.")
        return None

    try:
        account = web3.eth.accounts[0]
        transaction = {
            "from": account,
            "to": account,
            "value": 0,
            "data": web3.to_bytes(text=fingerprint),
            "gas": 100000,
            "gasPrice": web3.eth.gas_price,
            "nonce": web3.eth.get_transaction_count(account),
            "chainId": web3.eth.chain_id,
        }

        tx_hash = web3.eth.send_transaction(transaction)

        print("\n================================")
        print("BLOCKCHAIN RECORD CREATED")
        print("================================")
        print("Transaction hash:", tx_hash.hex())
        print("Fingerprint     :", fingerprint)
        print("================================")

        web3.eth.wait_for_transaction_receipt(tx_hash, timeout=10)
        return tx_hash.hex()
    except Exception as e:
        print(f"⚠️ Blockchain transaction error: {e}")
        return None


if __name__ == "__main__":
    test_fp = "6691dc75735f55d506261f7c80ebc8e004bdfb7c1628ccd3152ae99f02add1c8"
    tx_hash = write_fingerprint(test_fp)
    print("Result transaction hash:", tx_hash)
