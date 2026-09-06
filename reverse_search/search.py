from PIL import ImageCms
import os
import io
import hashlib
import requests
import numpy as np

from pathlib import Path
from PIL import Image
from dotenv import load_dotenv
from deepface import DeepFace
import serpapi

from reverse_search.face_id.face_id import (
    extract_face_embedding_from_pil,
    compare_face_embeddings,
)

load_dotenv()

SERPAPI_KEY = os.getenv("SERPAPI_KEY")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}


# ============================================================
# HELPERS
# ============================================================

def safe_text(value):
    if value is None:
        return ""
    return str(value).strip()


def normalize_url(url):
    if not url:
        return ""
    return str(url).strip().split("#")[0]


def platform_from_url(url):
    url = safe_text(url).lower()

    if "reddit.com" in url:
        return "Reddit"
    if "instagram.com" in url:
        return "Instagram"
    if "facebook.com" in url:
        return "Facebook"
    if "x.com" in url or "twitter.com" in url:
        return "X / Twitter"
    if "youtube.com" in url or "youtu.be" in url:
        return "YouTube"
    if "tiktok.com" in url:
        return "TikTok"
    if "pinterest.com" in url:
        return "Pinterest"
    if "linkedin.com" in url:
        return "LinkedIn"

    return "Web"


# ============================================================
# IMAGE DOWNLOAD
# ============================================================

def download_image(url, timeout=15):
    """
    Downloads an image from a URL.

    Returns:
        PIL.Image or None
    """

    if not url:
        return None

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=timeout,
            allow_redirects=True,
        )

        if response.status_code != 200:
            return None

        content_type = (
            response.headers.get(
                "content-type",
                ""
            ).lower()
        )

        # Reject obvious HTML pages.
        if (
            "text/html" in content_type
            or "application/json" in content_type
        ):
            return None

        if not response.content:
            return None

        image = Image.open(
            io.BytesIO(response.content)
        ).convert("RGB")

        if image.width < 80 or image.height < 80:
            return None

        return image

    except Exception:
        return None


def fetch_candidate_image(candidate):

    sources = []

    for key in [
        "image_url",
        "thumbnail",
        "original",
        "image",
        "thumbnail_url",
    ]:

        value = safe_text(
            candidate.get(key)
        )

        if value and value not in sources:
            sources.append(value)

    for source in sources:

        image = download_image(
            source
        )

        if image is not None:

            # Save first few downloaded images
            # for debugging only.
            try:

                debug_dir = Path(
                    "reverse_search/debug_candidates"
                )

                debug_dir.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                existing = list(
                    debug_dir.glob(
                        "candidate_*.jpg"
                    )
                )

                if len(existing) < 10:

                    debug_path = (
                        debug_dir
                        / f"candidate_{len(existing)+1}.jpg"
                    )

                    image.save(
                        debug_path,
                        "JPEG",
                    )

                    print(
                        f"    DEBUG IMAGE SAVED: "
                        f"{debug_path}"
                    )

            except Exception as e:

                print(
                    f"    DEBUG SAVE ERROR: {e}"
                )

            return image, source

    return None, ""

# ============================================================
# REAL PERCEPTUAL HASH
# ============================================================

def _dct_2d(matrix):
    """
    Small dependency-free 2D DCT-II.
    """

    matrix = np.asarray(
        matrix,
        dtype=np.float64,
    )

    n = matrix.shape[0]

    x = np.arange(n)
    k = np.arange(n)

    basis = np.cos(
        np.pi
        / n
        * (
            x[:, None] + 0.5
        )
        * k[None, :]
    )

    basis[:, 0] *= (
        1.0 / np.sqrt(2.0)
    )

    basis *= np.sqrt(
        2.0 / n
    )

    return (
        basis.T
        @ matrix
        @ basis
    )


def calculate_phash(image):
    """
    Standard-style perceptual hash using DCT.

    Returns a 64-bit hash string.
    """

    try:

        img = (
            image
            .convert("L")
            .resize(
                (32, 32),
                Image.Resampling.LANCZOS,
            )
        )

        pixels = np.asarray(
            img,
            dtype=np.float64,
        )

        dct = _dct_2d(
            pixels
        )

        # Use the top-left 8x8 low-frequency
        # coefficients.
        low_freq = dct[:8, :8]

        # Ignore DC coefficient when
        # calculating threshold.
        values = low_freq.flatten()

        median = np.median(
            values[1:]
        )

        bits = values > median

        return "".join(
            "1" if bit else "0"
            for bit in bits
        )

    except Exception:
        return None


def phash_distance(hash1, hash2):
    if not hash1 or not hash2:
        return 999

    if len(hash1) != len(hash2):
        return 999

    return sum(
        a != b
        for a, b in zip(
            hash1,
            hash2,
        )
    )


def phash_similarity(distance):
    """
    Converts Hamming distance into a
    conservative visual similarity score.

    0 distance  -> 100%
    32 distance -> 0%
    """

    if distance == 999:
        return 0.0

    score = (
        100.0
        * (
            1.0
            - (
                distance
                / 32.0
            )
        )
    )

    return max(
        0.0,
        min(
            100.0,
            score,
        ),
    )


# ============================================================
# CANDIDATE FACE DETECTION
# ============================================================

def extract_largest_face(image):
    """
    Detect and crop ONLY the candidate face.

    IMPORTANT:
    The original input image is NEVER cropped.
    """

    try:

        image_array = np.array(
            image.convert("RGB")
        )

        faces = DeepFace.extract_faces(
            img_path=image_array,
            detector_backend="opencv",
            enforce_detection=False,
            align=True,
        )

        if not faces:
            return None, False

        detected_faces = []

        for item in faces:

            face = item.get(
                "face"
            )

            if face is None:
                continue

            area_info = item.get(
                "facial_area",
                {},
            )

            width = area_info.get(
                "w",
                0,
            )

            height = area_info.get(
                "h",
                0,
            )

            area = (
                width * height
            )

            if area <= 0:

                try:
                    area = (
                        face.shape[0]
                        * face.shape[1]
                    )

                except Exception:
                    area = 0

            detected_faces.append(
                (
                    area,
                    face,
                )
            )

        if not detected_faces:
            return None, False

        detected_faces.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        _, face = (
            detected_faces[0]
        )

        face = np.asarray(
            face
        )

        if face.dtype != np.uint8:

            if face.max() <= 1.0:
                face = (
                    face
                    * 255.0
                )

            face = np.clip(
                face,
                0,
                255,
            ).astype(
                np.uint8
            )

        face_image = (
            Image.fromarray(
                face
            ).convert("RGB")
        )

        return (
            face_image,
            True,
        )

    except Exception:
        return None, False


def get_candidate_face_embedding(image):

    face_crop, detected = (
        extract_largest_face(
            image
        )
    )

    if not detected:
        return None, False

    if face_crop is None:
        return None, True

    try:

        embedding = (
            extract_face_embedding_from_pil(
                face_crop
            )
        )

        if embedding:
            return (
                embedding,
                True,
            )

    except Exception:
        pass

    return None, True


# ============================================================
# IMAGE VERIFICATION
# ============================================================

def verify_exact_image(
    visual_similarity,
    visual_distance,
    lens_type,
):
    """
    Strict exact/near-exact verification.

    Lens "exact" is accepted as exact.

    A visual result is NOT automatically exact.
    It needs an extremely small perceptual distance.
    """

    if lens_type == "exact":
        return True

    if (
        visual_distance != 999
        and visual_distance <= 2
    ):
        return True

    return False


# ============================================================
# SHA-256
# ============================================================

def sha256_text(text):
    return hashlib.sha256(
        text.encode(
            "utf-8",
            errors="replace",
        )
    ).hexdigest()


def build_fingerprint(candidate):

    data = "|".join(
        [
            safe_text(
                candidate.get(
                    "platform"
                )
            ),
            safe_text(
                candidate.get(
                    "title"
                )
            ),
            safe_text(
                candidate.get(
                    "url"
                )
            ),
            safe_text(
                candidate.get(
                    "match_category"
                )
            ),
        ]
    )

    return sha256_text(
        data
    )


def write_fingerprint(candidate):

    fingerprint = (
        build_fingerprint(
            candidate
        )
    )

    candidate[
        "fingerprint"
    ] = fingerprint

    return fingerprint


# ============================================================
# GOOGLE LENS
# ============================================================

def search_google_lens(image_path):

    print()
    print("================================")
    print("GOOGLE LENS REVERSE IMAGE SEARCH")
    print("================================")

    if not SERPAPI_KEY:
        print("SERPAPI_KEY not found.")

        return {
            "exact_matches": [],
            "visual_matches": [],
            "organic_results": [],
        }

    try:

        client = serpapi.Client(
            api_key=SERPAPI_KEY,
            timeout=60,
        )

        print(
            "Uploading original image "
            "to SerpApi..."
        )

        upload = client.upload_image(
            str(image_path)
        )

        image_id = upload.get("image_id")

        if not image_id:
            print("Image upload failed.")
            print(upload)

            return {
                "exact_matches": [],
                "visual_matches": [],
                "organic_results": [],
            }

        print("Image uploaded [OK]")

        print(
            "Running Google Lens..."
        )

        results = client.search({
            "engine": "google_lens",
            "image_id": image_id,
            "type": "all",
        })

        data = dict(results)

        exact = data.get(
            "exact_matches",
            [],
        )

        visual = data.get(
            "visual_matches",
            [],
        )

        organic = data.get(
            "organic_results",
            [],
        )

        print(
            f"Lens results: "
            f"{len(exact)} exact, "
            f"{len(visual)} visual, "
            f"{len(organic)} organic"
        )

        return {
            "exact_matches": exact,
            "visual_matches": visual,
            "organic_results": organic,
        }

    except Exception as e:

        print(
            f"Google Lens error: {e}"
        )

        return {
            "exact_matches": [],
            "visual_matches": [],
            "organic_results": [],
        }
# ============================================================
# RESULT CONVERSION
# ============================================================

def result_to_candidate(
    item,
    lens_type,
    lens_rank,
):

    if not isinstance(
        item,
        dict,
    ):
        return None

    url = (
        item.get("link")
        or item.get("url")
        or item.get("source")
        or ""
    )

    url = normalize_url(
        url
    )

    if not url:
        return None

    title = (
        item.get("title")
        or item.get("text")
        or item.get("name")
        or "Untitled result"
    )

    thumbnail = (
        item.get("thumbnail")
        or item.get("thumbnail_url")
        or ""
    )

    image_url = (
        item.get("original")
        or item.get("image_url")
        or item.get("image")
        or ""
    )

    return {

        # Result metadata
        "platform": platform_from_url(
            url
        ),

        "title": safe_text(
            title
        ),

        "url": url,

        # Image sources
        "thumbnail": safe_text(
            thumbnail
        ),

        "image_url": safe_text(
            image_url
        ),

        # Which Lens section
        "lens_match_type": lens_type,

        "lens_rank": lens_rank,

        # Ranking data
        "match_category": "Related Result",

        "visual_distance": 999,

        "visual_similarity": 0.0,

        "face_similarity": 0.0,

        "face_detected": False,

        "image_verified": False,

        "image_fetch_source": "",

        "confidence": 0.0,

        "fingerprint": None,

        "phash": None,

        # Actual downloaded image
        # stored for GUI use.
        "candidate_image": None,
    }


# ============================================================
# DEDUPLICATION
# ============================================================

def deduplicate_candidates(
    candidates
):

    seen = set()

    output = []

    for candidate in candidates:

        if not candidate:
            continue

        url = normalize_url(
            candidate.get(
                "url"
            )
        )

        if not url:
            continue

        key = url.lower()

        if key in seen:
            continue

        seen.add(key)

        output.append(
            candidate
        )

    return output


# ============================================================
# MATCH CLASSIFICATION
# ============================================================

CATEGORY_PRIORITY = {
    "Exact Image Match": 4,
    "Person Match": 3,
    "Visual Match": 2,
    "Related Result": 1,
}


def classify_candidate(
    candidate,
    input_is_face,
):

    lens_type = candidate.get(
        "lens_match_type"
    )

    visual = float(
        candidate.get(
            "visual_similarity",
            0.0,
        )
    )

    distance = int(
        candidate.get(
            "visual_distance",
            999,
        )
    )

    face = float(
        candidate.get(
            "face_similarity",
            0.0,
        )
    )

    face_detected = bool(
        candidate.get(
            "face_detected",
            False,
        )
    )

    image_verified = bool(
        candidate.get(
            "image_verified",
            False,
        )
    )

    # ========================================================
    # 1. EXACT IMAGE MATCH
    # ========================================================

    if image_verified and verify_exact_image(
        visual,
        distance,
        lens_type,
    ):

        candidate[
            "match_category"
        ] = "Exact Image Match"

        if lens_type == "exact":

            candidate[
                "confidence"
            ] = 99.0

        else:

            candidate[
                "confidence"
            ] = round(
                max(
                    97.0,
                    visual,
                ),
                2,
            )

        return candidate

    # ========================================================
    # 2. PERSON MATCH
    # ========================================================

    if (
        image_verified
        and input_is_face
        and face_detected
        and face >= 65.0
    ):

        candidate[
            "match_category"
        ] = "Person Match"

        # Face is the main evidence.
        # Visual is supporting evidence.
        score = (
            face * 0.85
            + visual * 0.15
        )

        candidate[
            "confidence"
        ] = round(
            min(
                96.0,
                score,
            ),
            2,
        )

        return candidate

    # ========================================================
    # 3. VISUAL MATCH
    # ========================================================

    if (
        image_verified
        and visual >= 30.0
    ):

        candidate[
            "match_category"
        ] = "Visual Match"

        score = visual

        # Lens itself selected this as
        # a visual match, so give a small
        # ranking bonus.
        if lens_type == "visual":
            score += 3.0

        candidate[
            "confidence"
        ] = round(
            min(
                92.0,
                score,
            ),
            2,
        )

        return candidate

    # ========================================================
    # 4. RELATED RESULT
    # ========================================================

    candidate[
        "match_category"
    ] = "Related Result"

    if image_verified:

        # We successfully downloaded the image
        # but it wasn't sufficiently similar.
        candidate[
            "confidence"
        ] = 20.0

    else:

        # We only know Lens returned the URL.
        candidate[
            "confidence"
        ] = 10.0

    return candidate


# ============================================================
# FINAL RANKING
# ============================================================

def rank_candidates(
    candidates,
    input_is_face,
):

    for candidate in candidates:

        classify_candidate(
            candidate,
            input_is_face,
        )

    def sort_key(candidate):

        category = candidate.get(
            "match_category",
            "Related Result",
        )

        priority = CATEGORY_PRIORITY.get(
            category,
            1,
        )

        confidence = float(
            candidate.get(
                "confidence",
                0.0,
            )
        )

        verified = (
            1
            if candidate.get(
                "image_verified",
                False,
            )
            else 0
        )

        lens_rank = int(
            candidate.get(
                "lens_rank",
                999,
            )
        )

        return (
            priority,
            verified,
            confidence,
            -lens_rank,
        )

    candidates.sort(
        key=sort_key,
        reverse=True,
    )

    for index, candidate in enumerate(
        candidates,
        start=1,
    ):

        candidate[
            "final_rank"
        ] = index

    return candidates


# ============================================================
# MAIN SEARCH
# ============================================================

def search_and_rank(
    image_path,
    input_face_embedding=None,
):

    image_path = Path(
        image_path
    )

    print()
    print("================================")
    print("VISUAL + FACE SEARCH")
    print("================================")

    # --------------------------------------------------------
    # ORIGINAL IMAGE
    # --------------------------------------------------------

    try:

        original_image = (
            Image.open(
                image_path
            ).convert("RGB")
        )

    except Exception as e:

        print(
            f"Unable to load input image: {e}"
        )

        return {
            "candidates": [],
            "best_match": None,
            "fingerprint": None,
        }

    # IMPORTANT:
    # Original image remains untouched.
    original_hash = calculate_phash(
        original_image
    )

    input_is_face = (
        input_face_embedding
        is not None
    )

    print(
        "Input mode: "
        + (
            "FACE + VISUAL"
            if input_is_face
            else "VISUAL"
        )
    )

    # --------------------------------------------------------
    # GOOGLE LENS
    # --------------------------------------------------------

    lens_data = search_google_lens(
        image_path
    )

    exact_items = lens_data.get(
        "exact_matches",
        [],
    )

    visual_items = lens_data.get(
        "visual_matches",
        [],
    )

    organic_items = lens_data.get(
        "organic_results",
        [],
    )

    # --------------------------------------------------------
    # BUILD CANDIDATES
    # --------------------------------------------------------

    candidates = []

    for rank, item in enumerate(
        exact_items,
        start=1,
    ):

        candidate = (
            result_to_candidate(
                item,
                "exact",
                rank,
            )
        )

        if candidate:
            candidates.append(
                candidate
            )

    for rank, item in enumerate(
        visual_items,
        start=1,
    ):

        candidate = (
            result_to_candidate(
                item,
                "visual",
                rank,
            )
        )

        if candidate:
            candidates.append(
                candidate
            )

    for rank, item in enumerate(
        organic_items,
        start=1,
    ):

        candidate = (
            result_to_candidate(
                item,
                "organic",
                rank,
            )
        )

        if candidate:
            candidates.append(
                candidate
            )

    candidates = (
        deduplicate_candidates(
            candidates
        )
    )

    print(
        f"Unique candidates collected: "
        f"{len(candidates)}"
    )

    # --------------------------------------------------------
    # LIMIT
    # --------------------------------------------------------

    candidates = candidates[:40]

    # --------------------------------------------------------
    # ANALYZE
    # --------------------------------------------------------

    print()
    print("================================")
    print("ANALYZING CANDIDATE IMAGES")
    print("================================")

    downloaded_count = 0
    unavailable_count = 0

    for index, candidate in enumerate(
        candidates,
        start=1,
    ):

        print(
            f"[{index}/{len(candidates)}] "
            f"{candidate['platform']} - "
            f"{candidate['title'][:70]}"
        )

        # ----------------------------------------------------
        # FETCH IMAGE
        # ----------------------------------------------------

        (
            candidate_image,
            source_url,
        ) = fetch_candidate_image(
            candidate
        )

        if candidate_image is None:

            unavailable_count += 1

            print(
                "    Image unavailable "
                "(image + thumbnail failed)"
            )

            # Do NOT pretend we compared it.
            candidate[
                "image_verified"
            ] = False

            continue

        downloaded_count += 1

        candidate[
            "image_verified"
        ] = True

        candidate[
            "image_fetch_source"
        ] = source_url

        # Store actual PIL image for GUI.
        candidate[
            "candidate_image"
        ] = candidate_image

        print(
            "    Candidate image fetched [OK]"
        )

        # ----------------------------------------------------
        # VISUAL COMPARISON
        # ----------------------------------------------------

        candidate_hash = (
            calculate_phash(
                candidate_image
            )
        )

        candidate[
            "phash"
        ] = candidate_hash

        distance = phash_distance(
            original_hash,
            candidate_hash,
        )

        candidate[
            "visual_distance"
        ] = distance

        visual_score = (
            phash_similarity(
                distance
            )
        )

        candidate[
            "visual_similarity"
        ] = round(
            visual_score,
            2,
        )

        # ----------------------------------------------------
        # FACE COMPARISON
        # ----------------------------------------------------

        if input_is_face:

            try:

                (
                    candidate_embedding,
                    face_detected,
                ) = get_candidate_face_embedding(
                    candidate_image
                )

                candidate[
                    "face_detected"
                ] = face_detected

                if (
                    face_detected
                    and candidate_embedding
                ):

                    face_score = (
                        compare_face_embeddings(
                            input_face_embedding,
                            candidate_embedding,
                        )
                    )

                    candidate[
                        "face_similarity"
                    ] = round(
                        face_score,
                        2,
                    )

                    print(
                        f"    Face: "
                        f"{face_score:.1f}% | "
                        f"Visual: "
                        f"{visual_score:.1f}%"
                    )

                else:

                    print(
                        f"    No candidate face | "
                        f"Visual: "
                        f"{visual_score:.1f}%"
                    )

            except Exception as e:

                print(
                    f"    Face analysis skipped: "
                    f"{e}"
                )

        else:

            print(
                f"    Visual: "
                f"{visual_score:.1f}%"
            )

    # --------------------------------------------------------
    # ANALYSIS SUMMARY
    # --------------------------------------------------------

    print()
    print("================================")
    print("IMAGE ANALYSIS SUMMARY")
    print("================================")

    print(
        f"Candidates received : "
        f"{len(candidates)}"
    )

    print(
        f"Images fetched      : "
        f"{downloaded_count}"
    )

    print(
        f"Images unavailable  : "
        f"{unavailable_count}"
    )

    # --------------------------------------------------------
    # RANK
    # --------------------------------------------------------

    ranked = rank_candidates(
        candidates,
        input_is_face,
    )

    # --------------------------------------------------------
    # FINAL RESULTS
    # --------------------------------------------------------

    print()
    print("================================")
    print("FINAL MATCH RANKING")
    print("================================")

    for candidate in ranked:

        print()
        print(
            f"Rank "
            f"{candidate.get('final_rank')}"
        )

        print(
            f"Category   : "
            f"{candidate.get('match_category')}"
        )

        print(
            f"Platform   : "
            f"{candidate.get('platform')}"
        )

        print(
            f"Title      : "
            f"{candidate.get('title')}"
        )

        print(
            f"Confidence : "
            f"{candidate.get('confidence', 0):.1f}%"
        )

        print(
            f"Visual     : "
            f"{candidate.get('visual_similarity', 0):.1f}%"
        )

        if input_is_face:

            print(
                f"Face       : "
                f"{candidate.get('face_similarity', 0):.1f}%"
            )

        print(
            f"Image      : "
            + (
                "Verified"
                if candidate.get(
                    "image_verified",
                    False,
                )
                else "Unavailable"
            )
        )

        print(
            f"Lens rank  : "
            f"{candidate.get('lens_rank', '-')}"
        )

        print(
            f"URL        : "
            f"{candidate.get('url')}"
        )

    # --------------------------------------------------------
    # BEST MATCH
    # --------------------------------------------------------

    best_match = (
        ranked[0]
        if ranked
        else None
    )

    # Do not select an unverified
    # candidate as the meaningful best match
    # when a verified candidate exists.

    verified_candidates = [
        candidate
        for candidate in ranked
        if candidate.get(
            "image_verified",
            False,
        )
    ]

    if verified_candidates:

        best_match = (
            verified_candidates[0]
        )

    fingerprint = None

    if best_match:

        fingerprint = (
            write_fingerprint(
                best_match
            )
        )

    # --------------------------------------------------------
    # BEST MATCH DISPLAY
    # --------------------------------------------------------

    print()
    print("================================")
    print("BEST MATCH")
    print("================================")

    if best_match:

        print(
            f"Rank       : "
            f"{best_match.get('final_rank')}"
        )

        print(
            f"Category   : "
            f"{best_match.get('match_category')}"
        )

        print(
            f"Platform   : "
            f"{best_match.get('platform')}"
        )

        print(
            f"Title      : "
            f"{best_match.get('title')}"
        )

        print(
            f"Confidence : "
            f"{best_match.get('confidence', 0):.1f}%"
        )

        print(
            f"Visual     : "
            f"{best_match.get('visual_similarity', 0):.1f}%"
        )

        if input_is_face:

            print(
                f"Face       : "
                f"{best_match.get('face_similarity', 0):.1f}%"
            )

        print(
            f"URL        : "
            f"{best_match.get('url')}"
        )

        print(
            f"Image      : "
            + (
                "Verified"
                if best_match.get(
                    "image_verified",
                    False,
                )
                else "Unavailable"
            )
        )

        if fingerprint:

            print(
                f"Fingerprint: "
                f"{fingerprint}"
            )

    else:

        print(
            "No candidate found."
        )

    print(
        "================================"
    )

    return {
        "candidates": ranked,
        "best_match": best_match,
        "fingerprint": fingerprint,
    }


# ============================================================
# DIRECT TEST
# ============================================================

if __name__ == "__main__":

    PROJECT_ROOT = (
        Path(__file__).resolve().parents[1]
    )

    test_image = (
        PROJECT_ROOT
        / "images.jpg"
    )

    if not test_image.exists():

        print(
            f"Test image not found: "
            f"{test_image}"
        )

    else:

        print(
            f"Testing image: "
            f"{test_image}"
        )

        embedding = None

        try:

            result = DeepFace.represent(
                img_path=str(test_image),
                model_name="Facenet512",
                detector_backend="opencv",
                enforce_detection=False,
            )

            if result:

                embedding = (
                    result[0].get(
                        "embedding"
                    )
                )

        except Exception as e:

            print(
                f"Face test skipped: {e}"
            )

        search_and_rank(
            test_image,
            embedding,
        )