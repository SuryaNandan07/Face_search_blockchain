
import os

from web3 import Web3
from dotenv import load_dotenv


# =========================================
# BLOCKCHAIN CONNECTION
# =========================================

def connect_blockchain():

    load_dotenv()

    rpc_url = os.getenv("RPC_URL")

    if not rpc_url:
        raise RuntimeError(
            "RPC_URL not found in .env"
        )

    web3 = Web3(
        Web3.HTTPProvider(rpc_url)
    )

    if not web3.is_connected():
        raise RuntimeError(
            "Could not connect to blockchain"
        )

    print("Blockchain connected!")
    print(
        "Chain ID:",
        web3.eth.chain_id
    )

    return web3


# =========================================
# WRITE FINGERPRINT
# =========================================

def write_fingerprint(fingerprint):

    web3 = connect_blockchain()

    # -----------------------------------------
    # Use first Ganache account
    # -----------------------------------------

    account = web3.eth.accounts[0]

    print(
        "Using account:",
        account
    )

    # -----------------------------------------
    # Validate fingerprint
    # -----------------------------------------

    if not fingerprint:
        raise ValueError(
            "Fingerprint cannot be empty."
        )

    print(
        "Fingerprint:",
        fingerprint
    )

    # -----------------------------------------
    # Build transaction
    # -----------------------------------------

    transaction = {
        "from": account,
        "to": account,
        "value": 0,
        "data": web3.to_bytes(
            text=fingerprint
        ),
        "gas": 100000,
        "gasPrice": web3.eth.gas_price,
        "nonce": web3.eth.get_transaction_count(
            account
        ),
        "chainId": web3.eth.chain_id,
    }

    # -----------------------------------------
    # Send transaction
    # -----------------------------------------

    tx_hash = web3.eth.send_transaction(
        transaction
    )

    print("\n================================")
    print("BLOCKCHAIN RECORD")
    print("================================")

    print(
        "Transaction hash:",
        tx_hash.hex()
    )

    print(
        "Fingerprint      :",
        fingerprint
    )

    print("================================")

    # -----------------------------------------
    # Wait for confirmation
    # -----------------------------------------

    receipt = (
        web3.eth.wait_for_transaction_receipt(
            tx_hash
        )
    )

    print("\nTransaction confirmed!")

    print(
        "Block number:",
        receipt.blockNumber
    )

    print(
        "Status      :",
        receipt.status
    )

    # -----------------------------------------
    # Return transaction hash
    # -----------------------------------------

    return tx_hash.hex()


# =========================================
# DIRECT TEST
# =========================================

if __name__ == "__main__":

    test_fingerprint = (
        "6691dc75735f55d506261f7c80ebc8e004bdfb7c1628ccd3152ae99f02add1c8"
    )

    tx_hash = write_fingerprint(
        test_fingerprint
    )

    print("\n================================")
    print("WRITE COMPLETE")
    print("================================")
    print("Transaction hash:", tx_hash)
