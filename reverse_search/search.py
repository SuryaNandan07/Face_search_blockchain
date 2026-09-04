import os
import sys
import hashlib
import requests
import imagehash

from io import BytesIO
from pathlib import Path
from PIL import Image
from rapidfuzz.fuzz import partial_ratio
import serpapi
from dotenv import load_dotenv


# =========================================
# SEARCH + RANK FUNCTION
# =========================================

def search_and_rank(image_path, search_context="La Peace"):

    # -----------------------------------------
    # Load environment variables
    # -----------------------------------------

    load_dotenv()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(
            encoding="utf-8",
            errors="replace"
        )

    # -----------------------------------------
    # Get SerpAPI key
    # -----------------------------------------

    api_key = os.getenv("SERPAPI_KEY")

    if not api_key:
        raise RuntimeError(
            "SERPAPI_KEY is not set. "
            "Please define SERPAPI_KEY in your .env file."
        )

    # -----------------------------------------
    # Create SerpAPI client
    # -----------------------------------------

    client = serpapi.Client(api_key=api_key)

    # -----------------------------------------
    # Validate image path
    # -----------------------------------------

    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(
            f"Image not found: {image_path}"
        )

    print("\n================================")
    print("REVERSE IMAGE SEARCH")
    print("================================")
    print("Image:", image_path)
    print("Search context:", search_context)

    # -----------------------------------------
    # Upload image
    # -----------------------------------------

    print("\nUploading image...")

    upload = client.upload_image(image_path)

    image_id = upload["image_id"]

    print("Image uploaded ✓")
    print("Image ID:", image_id)

    # -----------------------------------------
    # Google Lens search
    # -----------------------------------------

    print("\nSearching with Google Lens...")

    results = client.search({
        "engine": "google_lens",
        "image_id": image_id,
        "type": "all",
        "q": search_context,
    })

    # -----------------------------------------
    # Result statistics
    # -----------------------------------------

    print("\n================================")
    print("LENS RESULT TYPES")
    print("================================")

    print(
        "Exact matches :",
        len(results.get("exact_matches", []))
    )

    print(
        "Visual matches:",
        len(results.get("visual_matches", []))
    )

    print(
        "Organic results:",
        len(results.get("organic_results", []))
    )

    # -----------------------------------------
    # Social media platforms
    # -----------------------------------------

    social_platforms = {
        "instagram.com": "Instagram",
        "facebook.com": "Facebook",
        "x.com": "X",
        "twitter.com": "X",
        "reddit.com": "Reddit",
        "tiktok.com": "TikTok",
        "threads.com": "Threads",
    }

    # -----------------------------------------
    # Exact matches
    # -----------------------------------------

    print("\n================================")
    print("EXACT MATCHES")
    print("================================")

    for result in results.get("exact_matches", []):

        print(
            "Title:",
            result.get("title")
        )

        print(
            "URL:",
            result.get("link")
        )

        print(
            "Image:",
            result.get("thumbnail")
        )

    # -----------------------------------------
    # Collect social-media matches
    # -----------------------------------------

    matches = []

    # Used to prevent duplicate URLs
    seen_urls = set()

    # -----------------------------------------
    # Google Lens visual matches
    # -----------------------------------------

    for result in results.get("visual_matches", []):

        link = result.get("link", "")

        for domain, platform in social_platforms.items():

            if domain in link:

                if link in seen_urls:
                    break

                matches.append({
                    "platform": platform,
                    "title": result.get(
                        "title",
                        "Unknown"
                    ),
                    "url": link,
                    "thumbnail": result.get(
                        "thumbnail"
                    ),
                })

                seen_urls.add(link)

                break

    # -----------------------------------------
    # Google Lens organic results
    # -----------------------------------------

    for result in results.get("organic_results", []):

        link = result.get("link", "")

        for domain, platform in social_platforms.items():

            if domain in link:

                if link in seen_urls:
                    break

                matches.append({
                    "platform": platform,
                    "title": result.get(
                        "title",
                        "Unknown"
                    ),
                    "url": link,
                    "thumbnail": result.get(
                        "thumbnail"
                    ),
                })

                seen_urls.add(link)

                break

    # -----------------------------------------
    # Display social-media matches
    # -----------------------------------------

    print("\n================================")
    print("SOCIAL MEDIA MATCHES")
    print("================================")

    if not matches:

        print("No social-media matches found.")

    else:

        for i, match in enumerate(
            matches,
            start=1
        ):

            print(f"\nMatch {i}")

            print(
                f"Platform : {match['platform']}"
            )

            print(
                f"Title    : {match['title']}"
            )

            print(
                f"URL      : {match['url']}"
            )

            print(
                f"Thumbnail: {match.get('thumbnail')}"
            )

    # -----------------------------------------
    # Combined visual + text ranking
    # -----------------------------------------

    print("\n================================")
    print("COMBINED MATCH RANKING")
    print("================================")

    # -----------------------------------------
    # Open original image
    # -----------------------------------------

    original_image = (
        Image.open(image_path)
        .convert("RGB")
    )

    original_hash = imagehash.phash(
        original_image
    )

    ranked_matches = []

    # -----------------------------------------
    # Prepare search terms
    # -----------------------------------------

    context_terms = [
        term.strip().lower()
        for term in search_context.split(",")
        if term.strip()
    ]

    # Fallback terms for our demo
    if not context_terms:
        context_terms = [
            "la peace"
        ]

    # -----------------------------------------
    # Compare candidates
    # -----------------------------------------

    for match in matches:

        thumbnail_url = match.get(
            "thumbnail"
        )

        # We need an image for visual comparison
        if not thumbnail_url:
            continue

        try:

            # ---------------------------------
            # Download candidate thumbnail
            # ---------------------------------

            response = requests.get(
                thumbnail_url,
                timeout=15
            )

            response.raise_for_status()

            # ---------------------------------
            # Open candidate image
            # ---------------------------------

            candidate_image = Image.open(
                BytesIO(response.content)
            ).convert("RGB")

            # ---------------------------------
            # Calculate pHash
            # ---------------------------------

            candidate_hash = imagehash.phash(
                candidate_image
            )

            # Lower distance = more visually similar
            visual_distance = (
                original_hash - candidate_hash
            )

            # ---------------------------------
            # Convert distance to score
            # ---------------------------------

            visual_score = max(
                0,
                100 - (visual_distance * 3)
            )

            # ---------------------------------
            # Text relevance
            # ---------------------------------

            title = match.get(
                "title",
                ""
            ).lower()

            text_scores = [
                partial_ratio(
                    term,
                    title
                )
                for term in context_terms
            ]

            text_score = max(
                text_scores,
                default=0
            )

            # ---------------------------------
            # Final combined score
            # ---------------------------------

            final_score = (
                visual_score * 0.60
                + text_score * 0.40
            )

            # ---------------------------------
            # Save ranked result
            # ---------------------------------

            ranked_matches.append({

                "platform":
                    match["platform"],

                "title":
                    match["title"],

                "url":
                    match["url"],

                "thumbnail":
                    thumbnail_url,

                "visual_distance":
                    visual_distance,

                "visual_score":
                    visual_score,

                "text_score":
                    text_score,

                "final_score":
                    final_score,
            })

        except Exception as e:

            print(
                f"Could not compare "
                f"{match['url']}: {e}"
            )

    # -----------------------------------------
    # Sort highest score first
    # -----------------------------------------

    ranked_matches.sort(
        key=lambda x: x["final_score"],
        reverse=True
    )

    # -----------------------------------------
    # Display ranking
    # -----------------------------------------

    print("\nRanked candidates:")

    for rank, match in enumerate(
        ranked_matches,
        start=1
    ):

        print(f"\nRank {rank}")

        print(
            f"Platform        : "
            f"{match['platform']}"
        )

        print(
            f"Title           : "
            f"{match['title']}"
        )

        print(
            f"Visual distance : "
            f"{match['visual_distance']}"
        )

        print(
            f"Visual score    : "
            f"{match['visual_score']:.1f}"
        )

        print(
            f"Text score      : "
            f"{match['text_score']:.1f}"
        )

        print(
            f"FINAL SCORE     : "
            f"{match['final_score']:.1f}"
        )

        print(
            f"URL             : "
            f"{match['url']}"
        )

    # -----------------------------------------
    # Make sure we found a candidate
    # -----------------------------------------

    if not ranked_matches:

        raise RuntimeError(
            "No ranked social-media matches found."
        )

    # -----------------------------------------
    # Best candidate
    # -----------------------------------------

    best = ranked_matches[0]

    print("\n================================")
    print("BEST CANDIDATE")
    print("================================")

    print(
        "Platform    :",
        best["platform"]
    )

    print(
        "Title       :",
        best["title"]
    )

    print(
        "URL         :",
        best["url"]
    )

    print(
        "Final score :",
        f"{best['final_score']:.1f}"
    )

    print("================================")

    # -----------------------------------------
    # Generate SHA-256 fingerprint
    # -----------------------------------------

    matched_url = best["url"]

    matched_title = best["title"]

    matched_platform = best["platform"]

    # Deterministic record
    record_data = (
        f"{matched_platform}|"
        f"{matched_title}|"
        f"{matched_url}"
    )

    fingerprint = hashlib.sha256(
        record_data.encode("utf-8")
    ).hexdigest()

    # -----------------------------------------
    # Display fingerprint
    # -----------------------------------------

    print("\n================================")
    print("SHA-256 FINGERPRINT")
    print("================================")

    print(
        "Platform    :",
        matched_platform
    )

    print(
        "Title       :",
        matched_title
    )

    print(
        "URL         :",
        matched_url
    )

    print(
        "SHA-256     :",
        fingerprint
    )

    print("================================")

    # -----------------------------------------
    # Return data to main pipeline
    # -----------------------------------------

    return {
        "best_match": best,
        "fingerprint": fingerprint,
        "ranked_matches": ranked_matches,
    }


# =========================================
# DIRECT SCRIPT TEST
# =========================================

if __name__ == "__main__":

    # search.py is inside:
    #
    # Face_search_blockchain/
    # └── reverse_search/
    #     └── search.py
    #
    # Therefore parent.parent = project root

    PROJECT_ROOT = (
        Path(__file__)
        .resolve()
        .parent
        .parent
    )

    image_path = (
        PROJECT_ROOT
        / "reverse_search"
        / "images.jpg"
    )

    # Search context for the hackathon demo
    search_context = os.getenv(
        "SEARCH_CONTEXT",
        "La Peace"
    )

    result = search_and_rank(
        image_path,
        search_context
    )

    print("\n================================")
    print("SEARCH COMPLETED SUCCESSFULLY")
    print("================================")
