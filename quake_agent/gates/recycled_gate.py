from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Tuple, Optional, Set

class RecycledMediaGate:
    """
    Gate 3: Recycled Media & Duplicate Detection.
    Computes perceptual or cryptographic hashes to prevent re-analyzing
    identical duplicate images or images matched against a known prior catalog.
    """

    def __init__(self):
        self.seen_hashes: Set[str] = set()

    def check(self, file_path: Optional[str]) -> Tuple[bool, str, Optional[str]]:
        if not file_path or not Path(file_path).exists():
            return True, "No local file to hash; skipped duplicate gate", None

        # Compute hash
        try:
            h = self._compute_quick_hash(file_path)
            if h in self.seen_hashes:
                return False, f"Duplicate media detected (hash: {h[:8]} already processed)", h
            self.seen_hashes.add(h)
            return True, f"Unique media (hash: {h[:8]})", h
        except Exception as e:
            return True, f"Hash check skipped due to error: {e}", None

    def _compute_quick_hash(self, file_path: str) -> str:
        # Try imagehash (pHash) if available
        try:
            import imagehash
            from PIL import Image
            img = Image.open(file_path)
            return str(imagehash.phash(img))
        except Exception:
            pass

        # Fallback to sha256 of first 64KB
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            chunk = f.read(65536)
            hasher.update(chunk)
        return hasher.hexdigest()
