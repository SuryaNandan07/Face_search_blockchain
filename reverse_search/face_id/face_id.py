from pathlib import Path
from deepface import DeepFace


def detect_and_encode(image_path):
    image_path = Path(image_path)

    print("================================")
    print("FACE DETECTION + ENCODING")
    print("================================")

    print("Detecting face...")

    result = DeepFace.extract_faces(
        img_path=str(image_path),
        detector_backend="opencv",
        enforce_detection=True
    )

    print(f"Faces detected: {len(result)}")

    if len(result) == 0:
        raise RuntimeError("No face detected.")

    print("\nFace detected ✓")
    print("Generating face encoding...")

    embedding_result = DeepFace.represent(
        img_path=str(image_path),
        model_name="Facenet512",
        detector_backend="opencv",
        enforce_detection=True
    )

    embedding = embedding_result[0]["embedding"]

    print("Face encoding created ✓")
    print(f"Embedding dimensions: {len(embedding)}")
    print("================================")

    return embedding


if __name__ == "__main__":
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    image_path = PROJECT_ROOT / "reverse_search" / "images.jpg"

    detect_and_encode(image_path)