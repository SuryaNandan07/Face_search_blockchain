import sys
import numpy as np
from pathlib import Path
from PIL import Image
from deepface import DeepFace

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def detect_and_encode(image_path, enforce_detection=False):
    """
    Detects face in the image and returns FaceNet512 512-dimensional embedding.
    Returns None if no face is detected and enforce_detection is False.
    """
    image_path = Path(image_path)

    print("================================")
    print("FACE DETECTION + ENCODING")
    print("================================")
    print(f"Processing image: {image_path.name}")

    try:
        embedding_result = DeepFace.represent(
            img_path=str(image_path),
            model_name="Facenet512",
            detector_backend="opencv",
            enforce_detection=enforce_detection,
        )

        if not embedding_result or len(embedding_result) == 0:
            print("No face detected in input image.")
            print("================================")
            return None

        embedding = embedding_result[0].get("embedding")
        if embedding:
            print("Face detected [OK]")
            print(f"Embedding dimensions: {len(embedding)}")
            print("================================")
            return embedding

    except Exception as e:
        print(f"Face analysis note: {e}")

    print("No face detected in input image.")
    print("================================")
    return None


def extract_face_embedding_from_pil(pil_img):
    """
    Extract FaceNet512 embedding from an in-memory PIL Image.
    Returns None if no face detected or if error occurs.
    """
    try:
        img_array = np.array(pil_img.convert("RGB"))
        embedding_result = DeepFace.represent(
            img_path=img_array,
            model_name="Facenet512",
            detector_backend="opencv",
            enforce_detection=False,
        )
        if embedding_result and len(embedding_result) > 0:
            return embedding_result[0].get("embedding")
    except Exception:
        pass
    return None


def compare_face_embeddings(emb1, emb2):
    """
    Computes cosine distance between two FaceNet512 embedding vectors
    and converts it to a 0-100 similarity score.
    """
    if not emb1 or not emb2:
        return 0.0

    try:
        v1 = np.array(emb1, dtype=np.float64)
        v2 = np.array(emb2, dtype=np.float64)

        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        cosine_sim = np.dot(v1, v2) / (norm1 * norm2)
        cosine_distance = max(0.0, 1.0 - cosine_sim)

        # Facenet512 cosine distance threshold is ~0.45
        # Scale distance 0.0 -> 100%, 0.45 -> 0%
        similarity_score = max(0.0, min(100.0, 100.0 * (1.0 - (cosine_distance / 0.45))))
        return similarity_score
    except Exception:
        return 0.0


if __name__ == "__main__":
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    image_path = PROJECT_ROOT / "reverse_search" / "images.jpg"
    if image_path.exists():
        emb = detect_and_encode(image_path)
        print("Embedding snippet:", emb[:5] if emb else "None")