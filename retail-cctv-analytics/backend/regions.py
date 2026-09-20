"""
User-Defined Regions Configuration Engine.
Enforces Universal Design:
- Zero assumed store layout, zero automatic shelf/checkout finding.
- The USER defines the Checkout Region and Shelf Region coordinates and names.
- Persists user configurations to config/regions.json.
"""

import os
import json
import numpy as np
import cv2
from dataclasses import dataclass, field, asdict
from typing import List, Tuple, Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config", "regions.json")

@dataclass
class UserRegion:
    region_id: str
    region_type: str  # "CHECKOUT" or "SHELF"
    name: str
    polygon: List[Tuple[int, int]]  # [(x, y), ...]
    color_rgb: Tuple[int, int, int]
    is_active: bool = True

class RegionManager:
    def __init__(self, frame_width: int = 640, frame_height: int = 480):
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.checkout_region: Optional[UserRegion] = None
        self.shelf_region: Optional[UserRegion] = None
        
        # Shelf baseline reference image (grayscale)
        self.shelf_baseline_roi: Optional[np.ndarray] = None
        self.full_baseline_gray: Optional[np.ndarray] = None
        self.shelf_baseline_edges: float = 0.0

        os.makedirs(os.path.join(BASE_DIR, "config"), exist_ok=True)
        self.load_configuration()

    def load_configuration(self):
        """Loads user-defined regions from disk or sets sensible initial default coordinates."""
        W, H = self.frame_width, self.frame_height
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                if "checkout" in data and data["checkout"]:
                    c = data["checkout"]
                    self.checkout_region = UserRegion(
                        region_id="checkout_region",
                        region_type="CHECKOUT",
                        name=c.get("name", "Main Checkout"),
                        polygon=[(int(p[0]), int(p[1])) for p in c.get("polygon", [])],
                        color_rgb=(186, 85, 211),
                    )
                if "shelf" in data and data["shelf"]:
                    s = data["shelf"]
                    self.shelf_region = UserRegion(
                        region_id="shelf_region",
                        region_type="SHELF",
                        name=s.get("name", "Shelf 1"),
                        polygon=[(int(p[0]), int(p[1])) for p in s.get("polygon", [])],
                        color_rgb=(255, 165, 0),
                    )
                return
            except Exception as e:
                print(f"[RegionManager] Could not load {CONFIG_FILE}: {e}")

        # Default initial user regions (can be moved or redrawn anytime by the user)
        self.shelf_region = UserRegion(
            region_id="shelf_region",
            region_type="SHELF",
            name="Shelf 1",
            polygon=[(int(W * 0.03), int(H * 0.15)), (int(W * 0.29), int(H * 0.15)),
                     (int(W * 0.29), int(H * 0.60)), (int(W * 0.03), int(H * 0.60))],
            color_rgb=(255, 165, 0),
        )

        self.checkout_region = UserRegion(
            region_id="checkout_region",
            region_type="CHECKOUT",
            name="Main Checkout",
            polygon=[(int(W * 0.65), int(H * 0.55)), (int(W * 0.95), int(H * 0.55)),
                     (int(W * 0.95), int(H * 0.95)), (int(W * 0.65), int(H * 0.95))],
            color_rgb=(186, 85, 211),
        )
        self.save_configuration()

    def save_configuration(self):
        """Persists user-drawn regions to disk."""
        data = {
            "checkout": asdict(self.checkout_region) if self.checkout_region else None,
            "shelf": asdict(self.shelf_region) if self.shelf_region else None,
        }
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[RegionManager] Error saving regions: {e}")

    def update_checkout_region(self, name: str, polygon: List[Tuple[int, int]]):
        self.checkout_region = UserRegion(
            region_id="checkout_region",
            region_type="CHECKOUT",
            name=name.strip() or "Main Checkout",
            polygon=[(int(p[0]), int(p[1])) for p in polygon],
            color_rgb=(186, 85, 211),
        )
        self.save_configuration()

    def update_shelf_region(self, name: str, polygon: List[Tuple[int, int]]):
        self.shelf_region = UserRegion(
            region_id="shelf_region",
            region_type="SHELF",
            name=name.strip() or "Shelf 1",
            polygon=[(int(p[0]), int(p[1])) for p in polygon],
            color_rgb=(255, 165, 0),
        )
        # Invalidate baseline so it will be recalibrated on next clean frame
        self.shelf_baseline_roi = None
        self.full_baseline_gray = None
        self.shelf_baseline_edges = 0.0
        self.save_configuration()

    def capture_shelf_baseline(self, frame: np.ndarray) -> bool:
        """Captures a clean reference baseline for the user-selected shelf region."""
        if self.shelf_region is None or frame is None or len(self.shelf_region.polygon) < 3:
            return False

        H, W = frame.shape[:2]
        mask = np.zeros((H, W), dtype=np.uint8)
        pts = np.array(self.shelf_region.polygon, dtype=np.int32)
        cv2.fillPoly(mask, [pts], 255)

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self.shelf_baseline_roi = cv2.bitwise_and(gray, gray, mask=mask)
        self.full_baseline_gray = gray.copy()

        edges = cv2.Canny(self.shelf_baseline_roi, 50, 150)
        edge_count = float(np.count_nonzero(edges & mask))
        poly_area = max(1.0, float(np.count_nonzero(mask)))
        self.shelf_baseline_edges = edge_count / poly_area
        return True

    @staticmethod
    def point_in_polygon(point: Tuple[int, int], polygon: List[Tuple[int, int]]) -> bool:
        """Tests whether a 2D point (x, y) is inside a polygon using OpenCV."""
        if not polygon or len(polygon) < 3:
            return False
        pts = np.array(polygon, dtype=np.int32)
        return cv2.pointPolygonTest(pts, (float(point[0]), float(point[1])), False) >= 0

    @staticmethod
    def check_bbox_polygon_overlap(bbox: Tuple[int, int, int, int], polygon: List[Tuple[int, int]]) -> float:
        """Computes approximate intersection fraction of a bounding box with a polygon."""
        if not polygon or len(polygon) < 3:
            return 0.0
        bx, by, bw, bh = bbox
        poly_pts = np.array(polygon, dtype=np.int32)
        test_points = [
            (bx, by), (bx + bw, by), (bx, by + bh), (bx + bw, by + bh),
            (bx + bw // 2, by + bh // 2), (bx + bw // 2, by + bh),
            (bx + bw // 2, by), (bx, by + bh // 2), (bx + bw, by + bh // 2)
        ]
        inside = sum(1 for p in test_points if cv2.pointPolygonTest(poly_pts, (float(p[0]), float(p[1])), False) >= 0)
        return inside / float(len(test_points))
