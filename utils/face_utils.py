import os
import numpy as np
from deepface import DeepFace
from multiprocessing import Pool, cpu_count

# Per-worker global model reference
_MODEL = None


def _init_worker():
    """Initializer for worker processes: load the ArcFace model once per process."""
    global _MODEL
    try:
        _MODEL = DeepFace.build_model('ArcFace')
    except Exception:
        _MODEL = None


def _process_single(image_path):
    """Process a single image and return its embedding (or zero-array on failure)."""
    global _MODEL
    try:
        # Call DeepFace.represent with the loaded model to avoid rebuilding it each call
        embedding_objs = DeepFace.represent(
            img_path=image_path,
            model=_MODEL,
            model_name='ArcFace',
            enforce_detection=False
        )

        if embedding_objs:
            return np.array(embedding_objs[0]["embedding"])
        return np.zeros(512)
    except Exception as e:
        print(f"Error processing image {image_path}: {e}")
        return np.zeros(512)


def process_images(image_paths, num_workers=None):
    """Compute embeddings for a list of image paths in parallel.

    - Uses a pool of worker processes. Each worker loads the ArcFace model once.
    - Returns a list of numpy arrays (embedding vectors) in the same order as input.
    """
    if not image_paths:
        return []

    # Choose reasonable default worker count
    max_workers = cpu_count()
    workers = num_workers if (isinstance(num_workers, int) and num_workers > 0) else max(1, min(max_workers, len(image_paths)))

    with Pool(processes=workers, initializer=_init_worker) as p:
        results = p.map(_process_single, image_paths)

    return results


def find_matching_images(reference_embedding, image_embeddings, threshold=0.65):
    """Find images with faces matching the reference image.

    Args:
        reference_embedding (numpy.array): Embedding of the reference face
        image_embeddings (list): List of embeddings of images to compare
        threshold (float): Similarity threshold (0-1)

    Returns:
        list: Indices of matching images
    """
    matched_indices = []

    for i, embedding in enumerate(image_embeddings):
        # Skip zero embeddings (images where no face was detected)
        if np.all(embedding == 0):
            continue

        # Calculate cosine similarity
        denom = (np.linalg.norm(reference_embedding) * np.linalg.norm(embedding))
        if denom == 0:
            continue
        similarity = np.dot(reference_embedding, embedding) / denom

        # If similarity is above threshold, it's a match
        if similarity >= threshold:
            matched_indices.append(i)

    return matched_indices