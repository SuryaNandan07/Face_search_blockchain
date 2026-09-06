import os
import sys
import hashlib
import tempfile
import urllib.parse
from pathlib import Path
from io import BytesIO

# Ensure project root is in sys.path for direct script execution
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests
import imagehash
from PIL import Image
import serpapi
from dotenv import load_dotenv

from reverse_search.face_id.face_id import (
    extract_face_embedding_from_pil,
    compare_face_embeddings,
)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        pass


# =========================================================
# PLATFORM DETECTION
# =========================================================

def get_platform_from_url(url):
    """Detect platform/source category from URL."""

    if not url:
        return "Website"

    url_lower = url.lower()

    platforms = [
        ("instagram.com", "Instagram"),
        ("facebook.com", "Facebook"),
        ("x.com", "X"),
        ("twitter.com", "X"),
        ("reddit.com", "Reddit"),
        ("tiktok.com", "TikTok"),
        ("threads.com", "Threads"),
        ("threads.net", "Threads"),
        ("youtube.com", "YouTube"),
        ("youtu.be", "YouTube"),
        ("pinterest.com", "Pinterest"),
        ("linkedin.com", "LinkedIn"),
        ("wikipedia.org", "Wikipedia"),
    ]

    for domain, platform in platforms:
        if domain in url_lower:
            return platform

    try:
        domain = urllib.parse.urlparse(url).netloc.lower()
        domain = domain.replace("www.", "")

        if domain:
            parts = domain.split(".")

            if len(parts) >= 2:
                return parts[-2].capitalize()

            return domain.capitalize()

    except Exception:
        pass

    return "Website"


# =========================================================
# IMAGE OPTIMIZATION
# =========================================================

def optimize_image_for_upload(image_path):
    """
    Prepare image for SerpApi upload.

    Original image is never modified.

    Creates a temporary JPEG if:
        - file > 1 MB
        OR
        - largest dimension > 1200 px
    """

    image_path = Path(image_path)

    file_size_mb = (
        image_path.stat().st_size
        / (1024 * 1024)
    )

    try:
        with Image.open(image_path) as img:

            width, height = img.size
            max_dim = max(width, height)

            if (
                file_size_mb <= 1.0
                and max_dim <= 1200
            ):
                return image_path, False

            temp_file = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".jpg",
            )

            temp_path = Path(temp_file.name)
            temp_file.close()

            img_copy = img.convert("RGB")

            img_copy.thumbnail(
                (1200, 1200),
                Image.Resampling.LANCZOS,
            )

            img_copy.save(
                temp_path,
                format="JPEG",
                quality=80,
                optimize=True,
            )

            print(
                f"Created temporary optimized copy: "
                f"{temp_path.name} "
                f"({temp_path.stat().st_size / 1024:.1f} KB)"
            )

            return temp_path, True

    except Exception as e:

        print(
            f"Image optimization warning: {e}. "
            f"Proceeding with original file."
        )

        return image_path, False


# =========================================================
# SHA-256
# =========================================================

def calculate_file_sha256(image_path):
    """Calculate SHA-256 of the original input file."""

    sha256 = hashlib.sha256()

    with open(image_path, "rb") as f:

        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            sha256.update(chunk)

    return sha256.hexdigest()


def create_no_match_fingerprint(image_path):
    """Create deterministic fingerprint for no-match result."""

    file_sha256 = calculate_file_sha256(
        image_path
    )

    record = f"NO_MATCH|{file_sha256}"

    return hashlib.sha256(
        record.encode("utf-8")
    ).hexdigest()


# =========================================================
# CANDIDATE HELPERS
# =========================================================

def build_candidate(
    item,
    match_type,
    default_title,
):
    """Normalize Google Lens result."""

    url = (
        item.get("link")
        or item.get("url")
        or ""
    ).strip()

    thumbnail = (
        item.get("thumbnail")
        or item.get("image")
        or item.get("original")
    )

    original = (
        item.get("original")
        or item.get("image")
        or thumbnail
    )

    return {
        "title": item.get(
            "title",
            default_title,
        ),
        "source": item.get(
            "source",
            get_platform_from_url(url),
        ),
        "url": url,
        "thumbnail": thumbnail,
        "image": original,
        "match_type": match_type,
        "position": item.get(
            "position",
            999,
        ),
    }


# =========================================================
# CANDIDATE IMAGE DOWNLOAD
# =========================================================

def download_candidate_image(
    url,
    headers,
):
    """
    Download candidate image.

    Returns:
        PIL.Image or None
    """

    if not url:
        return None

    try:

        response = requests.get(
            url,
            timeout=(2, 4),
            headers=headers,
        )

        if response.status_code != 200:
            return None

        if not response.content:
            return None

        if (
            len(response.content)
            > 8 * 1024 * 1024
        ):
            return None

        image = Image.open(
            BytesIO(response.content)
        ).convert("RGB")

        return image

    except Exception:
        return None


# =========================================================
# RANKING HELPERS
# =========================================================

def calculate_type_score(match_type):
    """
    Retrieval confidence supplied by Google Lens.

    Exact > Visual > Organic.
    """

    if match_type == "Exact Match":
        return 100.0

    if match_type == "Visual Match":
        return 85.0

    return 65.0


def calculate_phash_score(
    original_hash,
    candidate_image,
):
    """
    Compare perceptual hashes.

    Returns:
        distance, similarity score
    """

    candidate_hash = imagehash.phash(
        candidate_image
    )

    distance = (
        original_hash
        - candidate_hash
    )

    score = max(
        0.0,
        100.0 - (distance * 3.5),
    )

    return distance, score


# =========================================================
# MAIN SEARCH FUNCTION
# =========================================================

def search_and_rank(
    image_path,
    input_face_embedding=None,
):
    """
    Google Lens reverse image search + ranking.

    FACE INPUT:
        FaceNet512 is the primary identity signal.
        pHash and Lens retrieval type are supporting signals.

    NON-FACE INPUT:
        pHash + Lens retrieval type are used.

    IMPORTANT:
        Exact Lens matches are never treated as ordinary
        visual matches.
    """

    load_dotenv()

    api_key = os.getenv(
        "SERPAPI_KEY"
    )

    if not api_key:
        raise RuntimeError(
            "SERPAPI_KEY is not set. "
            "Please define SERPAPI_KEY in your .env file."
        )

    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(
            f"Image not found: {image_path}"
        )

    print("\n================================")
    print("REVERSE IMAGE SEARCH (GOOGLE LENS)")
    print("================================")

    print(
        "Input image:",
        image_path.name,
    )

    has_face = (
        input_face_embedding
        is not None
    )

    if has_face:
        print(
            "Face signal : Available [OK]"
        )
    else:
        print(
            "Face signal : None"
        )

    # -----------------------------------------------------
    # INPUT IMAGE
    # -----------------------------------------------------

    try:

        with Image.open(
            image_path
        ) as img:

            original_image = (
                img.convert("RGB")
            )

            original_hash = (
                imagehash.phash(
                    original_image
                )
            )

    except Exception as e:

        raise RuntimeError(
            f"Unable to read input image: {e}"
        )

    # -----------------------------------------------------
    # GOOGLE LENS
    # -----------------------------------------------------

    upload_path, is_temp = (
        optimize_image_for_upload(
            image_path
        )
    )

    try:

        print(
            "\nUploading image to Google Lens..."
        )

        client = serpapi.Client(
            api_key=api_key
        )

        upload = client.upload_image(
            upload_path
        )

        image_id = upload.get(
            "image_id"
        )

        if not image_id:
            raise RuntimeError(
                "SerpApi did not return an image_id."
            )

        print(
            "Image uploaded [OK] (ID:",
            image_id,
            ")",
        )

        print(
            "\nQuerying Google Lens API..."
        )

        results = client.search(
            {
                "engine": "google_lens",
                "image_id": image_id,
            }
        )

    except Exception as e:

        print(
            f"\nGoogle Lens search notice: {e}"
        )

        fingerprint = (
            create_no_match_fingerprint(
                image_path
            )
        )

        return {
            "best_match": None,
            "fingerprint": fingerprint,
            "ranked_matches": [],
            "status": "no_match",
            "message": str(e),
        }

    finally:

        if (
            is_temp
            and upload_path.exists()
        ):
            try:
                upload_path.unlink()
            except Exception:
                pass

    # -----------------------------------------------------
    # CANDIDATE DISCOVERY
    # -----------------------------------------------------

    exact_matches = results.get(
        "exact_matches",
        [],
    )

    visual_matches = results.get(
        "visual_matches",
        [],
    )

    organic_results = results.get(
        "organic_results",
        [],
    )

    print("\n================================")
    print("CANDIDATE DISCOVERY")
    print("================================")

    print(
        f"Exact matches   : "
        f"{len(exact_matches)}"
    )

    print(
        f"Visual matches  : "
        f"{len(visual_matches)}"
    )

    print(
        f"Organic results : "
        f"{len(organic_results)}"
    )

    raw_candidates = []

    # Exact results first.
    for item in exact_matches:

        raw_candidates.append(
            build_candidate(
                item,
                "Exact Match",
                "Exact Match Result",
            )
        )

    # Visual results second.
    for item in visual_matches:

        raw_candidates.append(
            build_candidate(
                item,
                "Visual Match",
                "Visual Match Result",
            )
        )

    # Organic results last.
    for item in organic_results:

        raw_candidates.append(
            build_candidate(
                item,
                "Organic Result",
                "Organic Search Result",
            )
        )

    # -----------------------------------------------------
    # DEDUPLICATE
    # -----------------------------------------------------

    candidates = []

    seen_urls = set()

    for candidate in raw_candidates:

        url = candidate["url"]

        if not url:
            continue

        normalized_url = url.rstrip("/")

        if normalized_url in seen_urls:
            continue

        seen_urls.add(
            normalized_url
        )

        candidate["platform"] = (
            get_platform_from_url(url)
        )

        candidates.append(
            candidate
        )

    print(
        "Unique candidates collected:",
        len(candidates),
    )

    if not candidates:

        fingerprint = (
            create_no_match_fingerprint(
                image_path
            )
        )

        return {
            "best_match": None,
            "fingerprint": fingerprint,
            "ranked_matches": [],
            "status": "no_match",
            "message": "No candidates returned.",
        }

    # -----------------------------------------------------
    # STAGE 1
    # FAST IMAGE COMPARISON
    # -----------------------------------------------------

    print("\n================================")
    print("STAGE 1: FAST VISUAL COMPARISON")
    print("================================")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    # -----------------------------------------------------
    # IMPORTANT CHANGE:
    #
    # Previously:
    #     candidates[:20]
    #
    # For face searches this could discard the actual
    # person result before FaceNet saw it.
    #
    # Now:
    #     face search -> up to 40 candidates
    #     normal search -> up to 30 candidates
    # -----------------------------------------------------

    if has_face:
        target_candidates = candidates[:40]
    else:
        target_candidates = candidates[:30]

    preliminary = []

    total = len(
        target_candidates
    )

    for idx, match in enumerate(
        target_candidates,
        start=1,
    ):

        print(
            f"Comparing candidate "
            f"{idx}/{total}..."
        )

        image_url = (
            match.get("thumbnail")
            or match.get("image")
        )

        if not image_url:

            print(
                "   Skipped: no candidate image"
            )

            continue

        candidate_image = (
            download_candidate_image(
                image_url,
                headers,
            )
        )

        if candidate_image is None:

            print(
                "   Skipped: image unavailable"
            )

            continue

        try:

            distance, phash_score = (
                calculate_phash_score(
                    original_hash,
                    candidate_image,
                )
            )

            type_score = (
                calculate_type_score(
                    match["match_type"]
                )
            )

            # Fast retrieval score.
            preliminary_score = (
                (type_score * 0.30)
                + (phash_score * 0.70)
            )

            preliminary.append(
                {
                    "match": match,
                    "image": candidate_image,
                    "visual_distance": distance,
                    "phash_score": phash_score,
                    "type_score": type_score,
                    "preliminary_score":
                        preliminary_score,
                }
            )

            print(
                f"   pHash similarity: "
                f"{phash_score:.1f}%"
            )

        except Exception as e:

            print(
                f"   Comparison failed: {e}"
            )

    print(
        f"\nFast comparison completed: "
        f"{len(preliminary)}/{total} candidates"
    )

    # -----------------------------------------------------
    # STAGE 2
    # FACE VERIFICATION
    # -----------------------------------------------------

    print("\n================================")
    print("STAGE 2: FACE VERIFICATION")
    print("================================")

    face_shortlist = []

    if has_face:

        # -------------------------------------------------
        # IMPORTANT:
        #
        # Do NOT select only the pHash winners.
        #
        # Exact Lens results always get included.
        # Then additional candidates are selected by
        # retrieval/pHash score.
        # -------------------------------------------------

        exact_items = [
            item
            for item in preliminary
            if item["match"]["match_type"]
            == "Exact Match"
        ]

        other_items = [
            item
            for item in preliminary
            if item["match"]["match_type"]
            != "Exact Match"
        ]

        other_items.sort(
            key=lambda x:
                x["preliminary_score"],
            reverse=True,
        )

        # Up to 10 FaceNet candidates.
        #
        # Exact matches are protected from being
        # removed by pHash.
        face_shortlist = (
            exact_items[:5]
            + other_items[:10]
        )

        # Remove duplicate object references.
        unique_shortlist = []

        seen_candidate_urls = set()

        for item in face_shortlist:

            candidate_url = (
                item["match"]["url"]
            )

            if candidate_url in seen_candidate_urls:
                continue

            seen_candidate_urls.add(
                candidate_url
            )

            unique_shortlist.append(
                item
            )

        face_shortlist = (
            unique_shortlist[:15]
        )

        print(
            "FaceNet512 shortlist:",
            len(face_shortlist),
            "candidates",
        )

    else:

        print(
            "No input face detected."
        )

        print(
            "FaceNet512 comparison skipped."
        )

    # -----------------------------------------------------
    # FINAL RANKING
    # -----------------------------------------------------

    print("\n================================")
    print("FINAL RANKING")
    print("================================")

    ranked_matches = []

    for item in preliminary:

        match = item["match"]

        face_score = None

        # -------------------------------------------------
        # FACE COMPARISON
        # -------------------------------------------------

        if item in face_shortlist:

            try:

                print(
                    "Face comparison:",
                    match["title"][:60],
                )

                candidate_face_embedding = (
                    extract_face_embedding_from_pil(
                        item["image"]
                    )
                )

                if (
                    candidate_face_embedding
                    is not None
                ):

                    face_score = (
                        compare_face_embeddings(
                            input_face_embedding,
                            candidate_face_embedding,
                        )
                    )

                    print(
                        f"   Face similarity: "
                        f"{face_score:.1f}%"
                    )

                else:

                    print(
                        "   No face in candidate."
                    )

            except Exception as e:

                print(
                    "   Face comparison failed:",
                    e,
                )

        # -------------------------------------------------
        # FINAL CONFIDENCE
        # -------------------------------------------------

        type_score = (
            item["type_score"]
        )

        phash_score = (
            item["phash_score"]
        )

        if has_face:

            # ---------------------------------------------
            # FACE SEARCH
            #
            # Face identity is the strongest signal.
            #
            # FaceNet     = 65%
            # pHash       = 20%
            # Lens type   = 15%
            #
            # If no face is found in the candidate,
            # it cannot receive the full identity score.
            # ---------------------------------------------

            if face_score is not None:

                confidence = (
                    (face_score * 0.65)
                    + (phash_score * 0.20)
                    + (type_score * 0.15)
                )

            else:

                # Candidate did not contain a usable face.
                # Penalize it heavily instead of allowing
                # clothing/background similarity to dominate.
                confidence = (
                    (phash_score * 0.25)
                    + (type_score * 0.15)
                )

        else:

            # ---------------------------------------------
            # NON-FACE SEARCH
            #
            # Keep visual similarity as the main signal.
            # ---------------------------------------------

            confidence = (
                (type_score * 0.30)
                + (phash_score * 0.70)
            )

        # -------------------------------------------------
        # EXACT MATCH PROTECTION
        # -------------------------------------------------

        if (
            match["match_type"]
            == "Exact Match"
        ):

            if has_face and face_score is not None:

                # Exact + verified face.
                confidence = max(
                    confidence,
                    95.0,
                )

            elif not has_face:

                # Exact Lens result for non-face input.
                confidence = max(
                    confidence,
                    95.0,
                )

        confidence = round(
            max(
                0.0,
                min(
                    100.0,
                    confidence,
                ),
            ),
            1,
        )

        ranked_matches.append(
            {
                "platform": match["platform"],
                "source": match["source"],
                "title": match["title"],
                "url": match["url"],
                "thumbnail": (
                    match.get("thumbnail")
                    or match.get("image")
                ),
                "match_type": match["match_type"],
                "visual_distance":
                    item["visual_distance"],
                "phash_score":
                    round(
                        phash_score,
                        1,
                    ),
                "face_score":
                    (
                        round(
                            face_score,
                            1,
                        )
                        if face_score is not None
                        else None
                    ),
                "confidence": confidence,
            }
        )

    # -----------------------------------------------------
    # SORT
    # -----------------------------------------------------

    # Exact matches are always placed before visual/
    # organic results when their evidence is comparable.
    #
    # Confidence remains the primary numerical ranking.

    ranked_matches.sort(
        key=lambda x: (
            x["confidence"],
            1
            if x["match_type"]
            == "Exact Match"
            else 0,
        ),
        reverse=True,
    )

    # -----------------------------------------------------
    # NO MATCH
    # -----------------------------------------------------

    if not ranked_matches:

        print(
            "\n[NOTE] No usable candidate images "
            "were available."
        )

        fingerprint = (
            create_no_match_fingerprint(
                image_path
            )
        )

        return {
            "best_match": None,
            "fingerprint": fingerprint,
            "ranked_matches": [],
            "status": "no_match",
            "message": (
                "No usable candidate images found."
            ),
        }

    # -----------------------------------------------------
    # DISPLAY TOP RESULTS
    # -----------------------------------------------------

    print("\n================================")
    print("RANKED RESULTS")
    print("================================")

    for rank, candidate in enumerate(
        ranked_matches[:10],
        start=1,
    ):

        print(
            f"\nRank {rank}"
        )

        print(
            "Platform   :",
            candidate["platform"],
        )

        print(
            "Title      :",
            candidate["title"],
        )

        print(
            "Match Type :",
            candidate["match_type"],
        )

        print(
            "Confidence :",
            f"{candidate['confidence']}%",
        )

        print(
            "Visual Sim :",
            f"{candidate['phash_score']}%",
        )

        print(
            "Face Sim   :",
            (
                f"{candidate['face_score']}%"
                if candidate["face_score"]
                is not None
                else "N/A"
            ),
        )

        print(
            "URL        :",
            candidate["url"],
        )

    # -----------------------------------------------------
    # BEST MATCH
    # -----------------------------------------------------

    best = ranked_matches[0]

    print("\n================================")
    print("BEST CANDIDATE MATCH")
    print("================================")

    print(
        "Platform         :",
        best["platform"],
    )

    print(
        "Title            :",
        best["title"],
    )

    print(
        "URL              :",
        best["url"],
    )

    print(
        "Match Type       :",
        best["match_type"],
    )

    print(
        "Visual Similarity:",
        f"{best['phash_score']}%",
    )

    if best["face_score"] is not None:

        print(
            "Face Similarity  :",
            f"{best['face_score']}%",
        )

    else:

        print(
            "Face Similarity  : N/A"
        )

    print(
        "Overall Score    :",
        f"{best['confidence']}%",
    )

    print(
        "================================"
    )

    # -----------------------------------------------------
    # FINGERPRINT
    # -----------------------------------------------------

    record_data = (
        f"{best['platform']}|"
        f"{best['title']}|"
        f"{best['url']}"
    )

    fingerprint = hashlib.sha256(
        record_data.encode("utf-8")
    ).hexdigest()

    print(
        "\nSHA-256 Fingerprint:",
        fingerprint,
    )

    return {
        "best_match": best,
        "fingerprint": fingerprint,
        "ranked_matches": ranked_matches,
        "status": "success",
        "message": "Match found successfully.",
    }


# =========================================================
# DIRECT EXECUTION
# =========================================================

if __name__ == "__main__":

    sample_img = (
        PROJECT_ROOT
        / "reverse_search"
        / "images.jpg"
    )

    if not sample_img.exists():

        print(
            "Sample image not found:",
            sample_img,
        )

        sys.exit(1)

    result = search_and_rank(
        sample_img
    )

    print(
        "\nStatus:",
        result["status"],
    )

    print(
        "Fingerprint:",
        result["fingerprint"],
    )