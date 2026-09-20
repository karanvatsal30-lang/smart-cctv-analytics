"""
FEATURE 3: User-Defined Shelf Visual-Change Monitor.
Critical Requirements:
- Does NOT assume shelf location; monitors ONLY user-defined region.
- Never says "out of stock" or "shelf empty".
- Says "Visual change detected — Human verification recommended".
- CRITICAL SHELF/PERSON SEPARATION:
  * When a person walks in front of the shelf, reports:
    "Shelf view temporarily obstructed by person"
    and NEVER reports a shelf-change alert!
  * When the person leaves, waits for visual stability before comparing.
  * If lighting/obstruction prevents reliable analysis:
    "Unable to determine shelf change reliably"
"""

import cv2
import numpy as np
from dataclasses import dataclass
from typing import List, Any, Optional
from .regions import RegionManager, UserRegion

@dataclass
class ShelfReport:
    region_name: str
    status: str              # "No significant visual change detected", "Visual change detected", "Shelf view temporarily obstructed by person", "Unable to determine shelf change reliably"
    is_obstructed: bool
    is_changed: bool
    change_percentage: float
    reliability: str         # "High", "Medium", "Low", "Unavailable"
    explanation: str

class ShelfVisualChangeMonitor:
    def __init__(
        self,
        change_threshold_pct: float = 25.0,
        min_stable_frames: int = 5,
    ):
        self.change_threshold_pct = change_threshold_pct
        self.min_stable_frames = min_stable_frames
        
        # State tracking
        self.was_obstructed = False
        self.stable_frame_count = 0
        self.last_clean_frame: Optional[np.ndarray] = None

    def evaluate(
        self,
        frame: np.ndarray,
        active_tracks: List[Any],
        shelf_region: Optional[UserRegion],
        region_manager: RegionManager,
        video_quality_status: str = "HIGH",
    ) -> ShelfReport:
        """
        Evaluates visual changes in the user-selected shelf region.
        Guarantees: People standing in front are treated purely as obstructions,
        never as shelf alterations.
        """
        region_name = shelf_region.name if shelf_region else "Shelf Area"

        if shelf_region is None or not shelf_region.polygon or len(shelf_region.polygon) < 3:
            return ShelfReport(
                region_name=region_name,
                status="No shelf region configured",
                is_obstructed=False,
                is_changed=False,
                change_percentage=0.0,
                reliability="Unavailable",
                explanation="Draw a shelf monitoring region in settings to activate this feature.",
            )

        if frame is None or frame.size == 0:
            return ShelfReport(
                region_name=region_name,
                status="Unable to determine shelf change reliably",
                is_obstructed=False,
                is_changed=False,
                change_percentage=0.0,
                reliability="Unavailable",
                explanation="Video frame unavailable.",
            )

        # Environmental quality check (excessive blur, low light, severe glare)
        if video_quality_status in ("UNAVAILABLE", "LOW"):
            return ShelfReport(
                region_name=region_name,
                status="Unable to determine shelf change reliably",
                is_obstructed=False,
                is_changed=False,
                change_percentage=0.0,
                reliability="Low",
                explanation="Ambient lighting or video clarity too degraded for reliable comparison.",
            )

        # -------------------------------------------------------------
        # 1. CRITICAL OBSTRUCTION GATE: CHECK FOR PERSON IN FRONT OF SHELF
        # -------------------------------------------------------------
        person_obstructing = False
        for track in active_tracks:
            overlap = RegionManager.check_bbox_polygon_overlap(track.bbox, shelf_region.polygon)
            if overlap > 0.08:  # Person silhouette is partially or fully covering shelf view
                person_obstructing = True
                break

        if person_obstructing:
            self.was_obstructed = True
            self.stable_frame_count = 0
            return ShelfReport(
                region_name=region_name,
                status="Shelf view temporarily obstructed by person",
                is_obstructed=True,
                is_changed=False,
                change_percentage=0.0,
                reliability="High",
                explanation="Person visible in front of shelf; stock comparison paused to prevent false alerts.",
            )

        # -------------------------------------------------------------
        # 2. STABILIZATION WINDOW (Person just walked away)
        # -------------------------------------------------------------
        if self.was_obstructed:
            self.stable_frame_count += 1
            if self.stable_frame_count < self.min_stable_frames:
                return ShelfReport(
                    region_name=region_name,
                    status="Stabilizing shelf view...",
                    is_obstructed=False,
                    is_changed=False,
                    change_percentage=0.0,
                    reliability="Medium",
                    explanation=f"Person left shelf view; waiting for scene to stabilize ({self.stable_frame_count}/{self.min_stable_frames}).",
                )
            else:
                self.was_obstructed = False
                self.stable_frame_count = 0

        # -------------------------------------------------------------
        # 3. BASELINE REGISTRATION & COMPARISON
        # -------------------------------------------------------------
        H, W = frame.shape[:2]
        mask = np.zeros((H, W), dtype=np.uint8)
        pts = np.array(shelf_region.polygon, dtype=np.int32)
        cv2.fillPoly(mask, [pts], 255)
        poly_area = max(1.0, float(np.count_nonzero(mask)))

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        current_roi = cv2.bitwise_and(gray, gray, mask=mask)

        # Auto-initialize baseline if not yet set
        if region_manager.shelf_baseline_roi is None:
            region_manager.capture_shelf_baseline(frame)
            return ShelfReport(
                region_name=region_name,
                status="No significant visual change detected",
                is_obstructed=False,
                is_changed=False,
                change_percentage=0.0,
                reliability="High",
                explanation="Reference baseline captured. Monitoring for visual changes.",
            )

        # Measure pixel difference vs stored baseline
        baseline_roi = region_manager.shelf_baseline_roi
        # Ensure dimension matching if resolution changed
        if baseline_roi.shape != current_roi.shape:
            baseline_roi = cv2.resize(baseline_roi, (W, H))
            region_manager.shelf_baseline_roi = baseline_roi

        diff = cv2.absdiff(current_roi, baseline_roi)
        changed_pixels = np.count_nonzero(diff > 35)
        change_pct = round((changed_pixels / poly_area) * 100.0, 1)

        # Check for global frame lighting shift vs local shelf change
        # (If entire image changed brightness equally, it's an ambient lighting shift, not shelf change)
        mean_shelf_diff = np.mean(diff[mask > 0]) if poly_area > 0 else 0
        
        # Check brightness shift in the background outside the shelf region
        inv_mask = cv2.bitwise_not(mask)
        if region_manager.full_baseline_gray is not None:
            fb = region_manager.full_baseline_gray
            if fb.shape != gray.shape:
                fb = cv2.resize(fb, (W, H))
            bg_diff = cv2.absdiff(gray, fb)
            if np.count_nonzero(inv_mask) > 0:
                mean_bg_diff = float(np.mean(bg_diff[inv_mask > 0]))
            else:
                mean_bg_diff = float(np.mean(bg_diff))
        else:
            mean_bg_diff = 0.0

        if mean_shelf_diff > 40 and mean_bg_diff > 35:
            return ShelfReport(
                region_name=region_name,
                status="Unable to determine shelf change reliably",
                is_obstructed=False,
                is_changed=False,
                change_percentage=change_pct,
                reliability="Low",
                explanation="Global illumination shift detected across the entire camera view.",
            )

        if change_pct >= self.change_threshold_pct:
            return ShelfReport(
                region_name=region_name,
                status="Visual change detected",
                is_obstructed=False,
                is_changed=True,
                change_percentage=change_pct,
                reliability="Medium",
                explanation=f"Significant visual difference ({change_pct:.0f}%) observed in {region_name}. Human verification recommended.",
            )
        else:
            return ShelfReport(
                region_name=region_name,
                status="No significant visual change detected",
                is_obstructed=False,
                is_changed=False,
                change_percentage=change_pct,
                reliability="High",
                explanation=f"Visual appearance in {region_name} matches reference baseline.",
            )
