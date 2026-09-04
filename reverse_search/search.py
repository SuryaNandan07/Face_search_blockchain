import os
import sys
import json
import hashlib
import requests
import imagehash

from io import BytesIO
from pathlib import Path
from PIL import Image
from rapidfuzz.fuzz import partial_ratio
import serpapi
from dotenv import load_dotenv
# Load environment variables from .env file
load_dotenv()

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


# Get API key from environment variable
api_key = os.getenv("SERPAPI_KEY")

if not api_key:
    raise RuntimeError("SERPAPI_KEY is not set. Please define SERPAPI_KEY in your .env file.")


# Create client
client = serpapi.Client(api_key=api_key)

# Test image
image_path = "download.jpg"

print("Uploading image...")
upload = client.upload_image(image_path)

print("Searching with Google Lens...")
results = client.search({
    "engine": "google_lens",
    "image_id": upload["image_id"],
    "type": "all",
})
print("\n================================")
print("LENS RESULT TYPES")
print("================================")

print("Exact matches :", len(results.get("exact_matches", [])))
print("Visual matches:", len(results.get("visual_matches", [])))
print("Organic results:", len(results.get("organic_results", [])))
# -----------------------------------------
# Find social-media results
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

print("\n================================")
print("EXACT MATCHES")
print("================================")

for result in results.get("exact_matches", []):
    print("Title:", result.get("title"))
    print("URL:", result.get("link"))
    print("Image:", result.get("thumbnail"))

matches = []

# Google Lens visual matches
for result in results.get("visual_matches", []):
    link = result.get("link", "")

    for domain, platform in social_platforms.items():
        if domain in link:
            matches.append({
                "platform": platform,
                "title": result.get("title", "Unknown"),
                "url": link,
                "thumbnail": result.get("thumbnail"),
            })
            break

# Google Lens organic results
for result in results.get("organic_results", []):
    link = result.get("link", "")

    for domain, platform in social_platforms.items():
        if domain in link:
            matches.append({
                "platform": platform,
                "title": result.get("title", "Unknown"),
                "url": link,
            })
            break


# -----------------------------------------
# Display matches
# -----------------------------------------

print("\n================================")
print("SOCIAL MEDIA MATCHES")
print("================================")

if not matches:
    print("No social-media matches found.")
else:
    for i, match in enumerate(matches, start=1):
        print(f"\nMatch {i}")
        print(f"Platform : {match['platform']}")
        print(f"Title    : {match['title']}")
        print(f"URL      : {match['url']}")
        print(f"Thumbnail : {match.get('thumbnail')}")

print("\n================================")
# -----------------------------------------
# Combined visual + text ranking
# -----------------------------------------

TARGET_TERMS = [
    "la peace",
    "kai cenat",
    "minecraft",
]

print("\n================================")
print("COMBINED MATCH RANKING")
print("================================")

original_image = Image.open(image_path).convert("RGB")
original_hash = imagehash.phash(original_image)

ranked_matches = []

for match in matches:

    thumbnail_url = match.get("thumbnail")

    if not thumbnail_url:
        continue

    try:
        response = requests.get(thumbnail_url, timeout=15)
        response.raise_for_status()

        candidate_image = Image.open(
            BytesIO(response.content)
        ).convert("RGB")

        candidate_hash = imagehash.phash(candidate_image)

        # Lower = visually closer
        visual_distance = original_hash - candidate_hash

        # Convert distance into a visual score
        visual_score = max(0, 100 - (visual_distance * 3))

        # Check title relevance
        title = match.get("title", "").lower()

        text_scores = [
            partial_ratio(term, title)
            for term in TARGET_TERMS
        ]

        text_score = max(text_scores)

        # Combined score
        final_score = (
            visual_score * 0.60
            + text_score * 0.40
        )

        ranked_matches.append({
            "platform": match["platform"],
            "title": match["title"],
            "url": match["url"],
            "thumbnail": thumbnail_url,
            "visual_distance": visual_distance,
            "visual_score": visual_score,
            "text_score": text_score,
            "final_score": final_score,
        })

    except Exception as e:
        print(f"Could not compare {match['url']}: {e}")


# Highest final score first
ranked_matches.sort(
    key=lambda x: x["final_score"],
    reverse=True
)


print("\nRanked candidates:")

for rank, match in enumerate(ranked_matches, start=1):

    print(f"\nRank {rank}")
    print(f"Platform        : {match['platform']}")
    print(f"Title           : {match['title']}")
    print(f"Visual distance : {match['visual_distance']}")
    print(f"Visual score    : {match['visual_score']:.1f}")
    print(f"Text score      : {match['text_score']:.1f}")
    print(f"FINAL SCORE     : {match['final_score']:.1f}")
    print(f"URL             : {match['url']}")


print("\n================================")

if ranked_matches:
    best = ranked_matches[0]

    print("BEST CANDIDATE")
    print("================================")
    print("Platform    :", best["platform"])
    print("Title       :", best["title"])
    print("URL         :", best["url"])
    print("Final score :", f"{best['final_score']:.1f}")
    print("================================")

    # -----------------------------------------
    # Generate SHA-256 fingerprint
    # -----------------------------------------

    if not ranked_matches:
        raise RuntimeError("No ranked social-media matches found.")

    best = ranked_matches[0]

    matched_url = best["url"]
    matched_title = best["title"]
    matched_platform = best["platform"]

    record_data = (
        f"{matched_platform}|"
        f"{matched_title}|"
        f"{matched_url}"
    )

    fingerprint = hashlib.sha256(
        record_data.encode("utf-8")
    ).hexdigest()

    print("\n================================")
    print("SHA-256 FINGERPRINT")
    print("================================")
    print("Platform    :", matched_platform)
    print("Title       :", matched_title)
    print("URL         :", matched_url)
    print("SHA-256     :", fingerprint)
    print("================================")