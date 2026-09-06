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


def verify_fingerprint(transaction_hash, original_fingerprint):
    """
    Reads a transaction from the blockchain and verifies if the stored
    fingerprint matches original_fingerprint.
    """
    if not transaction_hash or not original_fingerprint:
        return False

    web3 = connect_blockchain()
    if not web3:
        print("⚠️ Blockchain Notice: Local Ganache node is offline. Cannot verify transaction on-chain.")
        return False

    try:
        print("\nReading blockchain transaction...")
        tx = web3.eth.get_transaction(transaction_hash)

        stored_fingerprint = web3.to_text(tx["input"]).rstrip("\x00")

        verified = (stored_fingerprint == original_fingerprint)

        print("\n================================")
        print("BLOCKCHAIN VERIFICATION")
        print("================================")
        print("Transaction  :", transaction_hash)
        print("Block Number :", tx.get("blockNumber"))
        print("Stored Hash  :", stored_fingerprint)
        print("Original Hash:", original_fingerprint)

        if verified:
            print("\n✅ VERIFICATION SUCCESSFUL: Fingerprint matches blockchain record.")
        else:
            print("\n❌ VERIFICATION FAILED: Fingerprint mismatch.")
        print("================================")

        return verified
    except Exception as e:
        print(f"⚠️ Blockchain verification error: {e}")
        return False


if __name__ == "__main__":
    tx_hash = "e6c677151139db70d10ed577c75b29fc9b8ee9a318e627867c74210e204c48d6"
    test_fp = "6691dc75735f55d506261f7c80ebc8e004bdfb7c1628ccd3152ae99f02add1c8"
    print("Verification:", verify_fingerprint(tx_hash, test_fp))
