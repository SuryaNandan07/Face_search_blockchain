
from pathlib import Path

from reverse_search.face_id.face_id import detect_and_encode
from reverse_search.search import search_and_rank

from blockchain.write_record import write_fingerprint
from blockchain.verify_record import verify_fingerprint


# =========================================
# PROJECT CONFIGURATION
# =========================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

IMAGE_PATH = (
    PROJECT_ROOT
    / "reverse_search"
    / "images.jpg"
)

SEARCH_CONTEXT = "La Peace"


# =========================================
# MAIN PIPELINE
# =========================================

def main():

    print("\n")
    print("========================================")
    print("     FACE SEARCH + BLOCKCHAIN SYSTEM")
    print("========================================")

    # -----------------------------------------
    # Check input image
    # -----------------------------------------

    if not IMAGE_PATH.exists():

        raise FileNotFoundError(
            f"Input image not found: {IMAGE_PATH}"
        )

    print("\nInput image:")
    print(IMAGE_PATH)

    # =========================================
    # STEP 1 — FACE DETECTION + ENCODING
    # =========================================

    print("\n")
    print("========================================")
    print("STEP 1 — FACE DETECTION + ENCODING")
    print("========================================")

    embedding = detect_and_encode(
        IMAGE_PATH
    )

    print("\nFace embedding generated ✓")
    print(
        "Embedding dimensions:",
        len(embedding)
    )

    # =========================================
    # STEP 2 — REVERSE IMAGE SEARCH
    # =========================================

    print("\n")
    print("========================================")
    print("STEP 2 — REVERSE IMAGE SEARCH")
    print("========================================")

    search_result = search_and_rank(
        IMAGE_PATH,
        SEARCH_CONTEXT
    )

    # -----------------------------------------
    # Extract search results
    # -----------------------------------------

    best_match = search_result[
        "best_match"
    ]

    fingerprint = search_result[
        "fingerprint"
    ]

    ranked_matches = search_result[
        "ranked_matches"
    ]

    print("\nSearch pipeline complete ✓")

    # =========================================
    # STEP 3 — BEST MATCH
    # =========================================

    print("\n")
    print("========================================")
    print("STEP 3 — SELECTED MATCH")
    print("========================================")

    print(
        "Platform    :",
        best_match["platform"]
    )

    print(
        "Title       :",
        best_match["title"]
    )

    print(
        "URL         :",
        best_match["url"]
    )

    print(
        "Final score :",
        f"{best_match['final_score']:.1f}"
    )

    # =========================================
    # STEP 4 — SHA-256
    # =========================================

    print("\n")
    print("========================================")
    print("STEP 4 — SHA-256 FINGERPRINT")
    print("========================================")

    print(
        "Fingerprint:",
        fingerprint
    )

    # =========================================
    # STEP 5 — WRITE TO BLOCKCHAIN
    # =========================================

    print("\n")
    print("========================================")
    print("STEP 5 — BLOCKCHAIN RECORD")
    print("========================================")

    transaction_hash = write_fingerprint(
        fingerprint
    )

    print("\nBlockchain record created ✓")

    print(
        "Transaction hash:",
        transaction_hash
    )

    # =========================================
    # STEP 6 — VERIFY BLOCKCHAIN RECORD
    # =========================================

    print("\n")
    print("========================================")
    print("STEP 6 — BLOCKCHAIN VERIFICATION")
    print("========================================")

    verified = verify_fingerprint(
        transaction_hash,
        fingerprint
    )

    # =========================================
    # FINAL RESULT
    # =========================================

    print("\n")
    print("========================================")
    print("           FINAL RESULT")
    print("========================================")

    print(
        "Best platform :",
        best_match["platform"]
    )

    print(
        "Best match    :",
        best_match["title"]
    )

    print(
        "Match score   :",
        f"{best_match['final_score']:.1f}"
    )

    print(
        "Fingerprint   :",
        fingerprint
    )

    print(
        "Transaction   :",
        transaction_hash
    )

    print(
        "Verified      :",
        verified
    )

    print("========================================")

    if verified:

        print(
            "\n✅ END-TO-END PIPELINE SUCCESSFUL"
        )

    else:

        print(
            "\n❌ BLOCKCHAIN VERIFICATION FAILED"
        )


# =========================================
# PROGRAM ENTRY POINT
# =========================================

if __name__ == "__main__":
    main()
