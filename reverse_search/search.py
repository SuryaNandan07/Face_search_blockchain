import os
import sys
import json
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
image_path = "reverse_search/download.jpg"

print("Uploading image...")
upload = client.upload_image(image_path)

print("Searching with Google Lens...")
results = client.search({
    "engine": "google_lens",
    "image_id": upload["image_id"],
})

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

print("\n================================")