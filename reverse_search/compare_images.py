from pathlib import Path
import requests
from PIL import Image
import imagehash
from io import BytesIO

PROJECT_ROOT = Path(__file__).resolve().parent.parent
input_image = PROJECT_ROOT / "reverse_search" / "images.jpg"

candidates = {
    2: {
        "url": "https://www.instagram.com/reel/Dcel545ij23/",
        "thumbnail": "https://encrypted-tbn2.gstatic.com/images?q=tbn:ANd9GcTOAlrp7aQQ68ejjAZW_Hszk9BbDhHPFwJ_7BvbMOWdLogFpxvs",
    },
    7: {
        "url": "https://www.instagram.com/p/DcbrASpkdqY/",
        "thumbnail": "https://encrypted-tbn3.gstatic.com/images?q=tbn:ANd9GcTM9MdUe_xBZqw0iZCEi5RWZ3XmpQt51iAOEHOZeoGLJvANA_ou",
    },
    8: {
        "url": "https://www.tiktok.com/discover/where-do-i-find-the-la-peace-clip",
        "thumbnail": "https://encrypted-tbn1.gstatic.com/images?q=tbn:ANd9GcRrV84g7b3R9I1fZepei80MWkhZ72BhnaOidqrLRdt0wffjXaPg",
    },
    14: {
        "url": "https://www.threads.com/@gio_palace/post/DcbT9dpESbu/kai-cenat-has-fully-embraced-his-viral-la-peace-meme-after-the-phrase-took-over/",
        "thumbnail": "https://encrypted-tbn3.gstatic.com/images?q=tbn:ANd9GcSkLh7yz_o22ZtdgkV0cQKeyaCbStgDm9UHPTCho3f9GBqgoQxW",
    },
    15: {
        "url": "https://www.tiktok.com/@halfoo_edit/video/7678289692403567893",
        "thumbnail": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTVF_DeD2-9A2-CPBp3JjsplEwLgyIHRD5qFmcp59GKz7fyjOJ8",
    },
}

original = Image.open(input_image).convert("RGB")
original_hash = imagehash.phash(original)

results = []

print("================================")
print("CANDIDATE IMAGE COMPARISON")
print("================================")

for match_number, candidate in candidates.items():

    try:
        response = requests.get(candidate["thumbnail"], timeout=15)
        response.raise_for_status()

        image = Image.open(BytesIO(response.content)).convert("RGB")
        candidate_hash = imagehash.phash(image)

        distance = original_hash - candidate_hash

        results.append({
            "match": match_number,
            "url": candidate["url"],
            "distance": distance,
        })

        print(f"Match {match_number:<2} → distance: {distance}")

    except Exception as e:
        print(f"Match {match_number:<2} → ERROR: {e}")

print("\n================================")

if results:
    best = min(results, key=lambda x: x["distance"])

    print("BEST VISUAL MATCH")
    print("================================")
    print("Match    :", best["match"])
    print("Distance :", best["distance"])
    print("URL      :", best["url"])

print("================================")