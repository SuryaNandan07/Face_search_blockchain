import os
import sys
import hashlib
import tempfile
import urllib.parse
from pathlib import Path

# Ensure project root is in sys.path for direct script execution
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests
import imagehash
from io import BytesIO
from PIL import Image
import serpapi
from dotenv import load_dotenv

from reverse_search.face_id.face_id import (
    extract_face_embedding_from_pil,
    compare_face_embeddings,
)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def get_platform_from_url(url):
    """Detects platform/source category from a URL."""
    if not url:
        return "Website"

    url_lower = url.lower()
    if "instagram.com" in url_lower:
        return "Instagram"
    if "facebook.com" in url_lower:
        return "Facebook"
    if "x.com" in url_lower or "twitter.com" in url_lower:
        return "X"
    if "reddit.com" in url_lower:
        return "Reddit"
    if "tiktok.com" in url_lower:
        return "TikTok"
    if "threads.com" in url_lower or "threads.net" in url_lower:
        return "Threads"
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "YouTube"
    if "pinterest.com" in url_lower:
        return "Pinterest"
    if "linkedin.com" in url_lower:
        return "LinkedIn"
    if "wikipedia.org" in url_lower:
        return "Wikipedia"

    try:
        domain = urllib.parse.urlparse(url).netloc
        domain = domain.replace("www.", "")
        if domain:
            parts = domain.split(".")
            if len(parts) >= 2:
                return parts[0].capitalize()
            return domain.capitalize()
    except Exception:
        pass

    return "Website"


def optimize_image_for_upload(image_path):
    """
    Inspects image file size and dimensions.
    Creates a temporary compressed copy if image > 1 MB or max side > 1200px.
    Returns (path_to_upload, is_temporary_boolean).
    """
    image_path = Path(image_path)
    file_size_mb = image_path.stat().st_size / (1024 * 1024)

    try:
        with Image.open(image_path) as img:
            width, height = img.size
            max_dim = max(width, height)

            # If file size <= 1 MB and max side <= 1200px, use original file
            if file_size_mb <= 1.0 and max_dim <= 1200:
                return image_path, False

            # Create temporary resized image for SerpApi upload
            temp_file = tempfile.NamedTemporaryFile(
                delete=False, suffix=".jpg"
            )
            temp_path = Path(temp_file.name)
            temp_file.close()

            # Resize while maintaining aspect ratio
            img_copy = img.convert("RGB")
            img_copy.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
            img_copy.save(temp_path, format="JPEG", quality=80)

            print(f"Created temporary optimized copy: {temp_path.name} ({temp_path.stat().st_size / 1024:.1f} KB)")
            return temp_path, True
    except Exception as e:
        print(f"Image optimization warning: {e}. Proceeding with original file.")
        return image_path, False


def search_and_rank(image_path, input_face_embedding=None):
    """
    Performs Google Lens reverse search on an arbitrary image,
    builds a normalized candidate pool, ranks candidates using visual pHash
    and optional face embedding similarity, and computes a SHA-256 fingerprint.
    """
    load_dotenv()

    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        raise RuntimeError(
            "SERPAPI_KEY is not set. Please define SERPAPI_KEY in your .env file."
        )

    client = serpapi.Client(api_key=api_key)
    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    print("\n================================")
    print("REVERSE IMAGE SEARCH (GOOGLE LENS)")
    print("================================")
    print("Input image:", image_path.name)
    if input_face_embedding:
        print("Face signal : Available [OK]")
    else:
        print("Face signal : None (Non-face or undetected)")

    # -----------------------------------------
    # Image Upload & Lens Search
    # -----------------------------------------
    upload_path, is_temp = optimize_image_for_upload(image_path)

    try:
        print("\nUploading image to Google Lens...")
        upload = client.upload_image(upload_path)
        image_id = upload.get("image_id")

        if not image_id:
            raise RuntimeError("SerpApi did not return an image_id.")

        print("Image uploaded [OK] (ID:", image_id, ")")
        print("\nQuerying Google Lens API...")

        # Search Google Lens without hardcoded search queries
        results = client.search({
            "engine": "google_lens",
            "image_id": image_id,
        })
    except Exception as e:
        print(f"\n⚠️ Google Lens search notice: {e}")
        print("================================")

        with open(image_path, "rb") as f:
            img_bytes = f.read()
        file_sha256 = hashlib.sha256(img_bytes).hexdigest()
        no_match_record = f"NO_MATCH|{file_sha256}"
        fingerprint = hashlib.sha256(no_match_record.encode("utf-8")).hexdigest()

        return {
            "best_match": None,
            "fingerprint": fingerprint,
            "ranked_matches": [],
            "status": "no_match",
            "message": f"No reliable online match found ({e}).",
        }
    finally:
        if is_temp and upload_path.exists():
            try:
                upload_path.unlink()
            except Exception:
                pass

    # -----------------------------------------
    # Parse & Candidate Pool Discovery
    # -----------------------------------------
    exact_matches = results.get("exact_matches", [])
    visual_matches = results.get("visual_matches", [])
    organic_results = results.get("organic_results", [])

    print("\n================================")
    print("CANDIDATE DISCOVERY")
    print("================================")
    print(f"Exact matches   : {len(exact_matches)}")
    print(f"Visual matches  : {len(visual_matches)}")
    print(f"Organic results : {len(organic_results)}")

    raw_candidates = []

    for item in exact_matches:
        raw_candidates.append({
            "title": item.get("title", "Exact Match Result"),
            "source": item.get("source", get_platform_from_url(item.get("link", ""))),
            "url": item.get("link", ""),
            "thumbnail": item.get("thumbnail"),
            "image": item.get("original") or item.get("thumbnail"),
            "match_type": "Exact Match",
            "position": item.get("position", 1),
        })

    for item in visual_matches:
        raw_candidates.append({
            "title": item.get("title", "Visual Match Result"),
            "source": item.get("source", get_platform_from_url(item.get("link", ""))),
            "url": item.get("link", ""),
            "thumbnail": item.get("thumbnail"),
            "image": item.get("original") or item.get("thumbnail"),
            "match_type": "Visual Match",
            "position": item.get("position", 2),
        })

    for item in organic_results:
        raw_candidates.append({
            "title": item.get("title", "Organic Search Result"),
            "source": item.get("source", get_platform_from_url(item.get("link", ""))),
            "url": item.get("link", ""),
            "thumbnail": item.get("thumbnail"),
            "image": item.get("original") or item.get("thumbnail"),
            "match_type": "Organic Result",
            "position": item.get("position", 3),
        })

    # Deduplicate candidates by clean URL
    candidates = []
    seen_urls = set()

    for item in raw_candidates:
        url = item.get("url", "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        item["platform"] = get_platform_from_url(url)
        candidates.append(item)

    print(f"Unique candidates collected: {len(candidates)}")

    # -----------------------------------------
    # Visual & Face Ranking
    # -----------------------------------------
    print("\n================================")
    print("IMAGE-DRIVEN RANKING & COMPARISON")
    print("================================")

    original_image = Image.open(image_path).convert("RGB")
    original_hash = imagehash.phash(original_image)

    ranked_matches = []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }

    # Evaluate up to 25 top candidate matches
    target_candidates = candidates[:25]

    for idx, match in enumerate(target_candidates, start=1):
        thumb_url = match.get("thumbnail") or match.get("image")
        if not thumb_url:
            continue

        try:
            resp = requests.get(thumb_url, timeout=4, headers=headers)
            if resp.status_code != 200:
                continue

            candidate_pil = Image.open(BytesIO(resp.content)).convert("RGB")
            candidate_hash = imagehash.phash(candidate_pil)

            visual_distance = original_hash - candidate_hash
            phash_score = max(0.0, 100.0 - (visual_distance * 3.5))

            # Match type weight score
            m_type = match.get("match_type")
            if m_type == "Exact Match":
                type_score = 100.0
            elif m_type == "Visual Match":
                type_score = 85.0
            else:
                type_score = 65.0

            # Face comparison if face embedding present
            face_score = None
            if input_face_embedding is not None:
                cand_face_emb = extract_face_embedding_from_pil(candidate_pil)
                if cand_face_emb is not None:
                    face_score = compare_face_embeddings(
                        input_face_embedding, cand_face_emb
                    )

            # Combined Confidence Score
            if face_score is not None:
                confidence = (
                    (type_score * 0.20)
                    + (phash_score * 0.40)
                    + (face_score * 0.40)
                )
            else:
                confidence = (type_score * 0.30) + (phash_score * 0.70)

            confidence = round(max(0.0, min(100.0, confidence)), 1)

            ranked_matches.append({
                "platform": match["platform"],
                "source": match["source"],
                "title": match["title"],
                "url": match["url"],
                "thumbnail": thumb_url,
                "match_type": match["match_type"],
                "visual_distance": visual_distance,
                "phash_score": round(phash_score, 1),
                "face_score": round(face_score, 1) if face_score is not None else None,
                "confidence": confidence,
            })
        except Exception:
            pass

    # -----------------------------------------
    # Sort Candidates by Match Confidence
    # -----------------------------------------
    ranked_matches.sort(key=lambda x: x["confidence"], reverse=True)

    # -----------------------------------------
    # Handle Case Where No Match Is Found
    # -----------------------------------------
    if not ranked_matches:
        print("\n[NOTE] No reliable online match found for this image.")
        print("================================")

        # Generate deterministic input image hash for blockchain fingerprinting
        with open(image_path, "rb") as f:
            img_bytes = f.read()
        file_sha256 = hashlib.sha256(img_bytes).hexdigest()
        no_match_record = f"NO_MATCH|{file_sha256}"
        fingerprint = hashlib.sha256(no_match_record.encode("utf-8")).hexdigest()

        return {
            "best_match": None,
            "fingerprint": fingerprint,
            "ranked_matches": [],
            "status": "no_match",
            "message": "No reliable online match found.",
        }

    # -----------------------------------------
    # Select Best Candidate
    # -----------------------------------------
    best = ranked_matches[0]

    print("\n================================")
    print("BEST CANDIDATE MATCH")
    print("================================")
    print("Platform        :", best["platform"])
    print("Title           :", best["title"])
    print("URL             :", best["url"])
    print("Match Type      :", best["match_type"])
    print("Match Confidence:", f"{best['confidence']}%")
    print("================================")

    # Deterministic SHA-256 fingerprint from best match metadata
    record_data = f"{best['platform']}|{best['title']}|{best['url']}"
    fingerprint = hashlib.sha256(record_data.encode("utf-8")).hexdigest()

    return {
        "best_match": best,
        "fingerprint": fingerprint,
        "ranked_matches": ranked_matches,
        "status": "success",
        "message": "Match found successfully.",
    }


if __name__ == "__main__":
    sample_img = PROJECT_ROOT / "reverse_search" / "images.jpg"
    if sample_img.exists():
        res = search_and_rank(sample_img)
        print("Status:", res["status"])
        print("Fingerprint:", res["fingerprint"])
