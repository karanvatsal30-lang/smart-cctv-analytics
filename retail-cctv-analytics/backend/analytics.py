"""
Universal CCTV Analytics Engine.
Coordinates the EXACTLY 4 approved features independently:
FEATURE 1: Camera-Wide People Counting (Entire Frame)
FEATURE 2: User-Defined Checkout Congestion Monitoring
FEATURE 3: User-Defined Shelf Visual-Change Monitoring (with Obstruction Gate)
FEATURE 4: Video / Analytics Reliability Monitoring
"""

import time
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import cv2

from .validator import EvidenceValidator, ReliabilityReport
from .detector import AnonymousPersonDetector
from .tracker import AnonymousTracker, Tracklet
from .regions import RegionManager, UserRegion
from .checkout_monitor import CheckoutCongestionMonitor, CheckoutReport
from .shelf_monitor import ShelfVisualChangeMonitor, ShelfReport

class StoreAnalyticsEngine:
    def __init__(self, frame_width: int = 640, frame_height: int = 480):
        self.frame_width = frame_width
        self.frame_height = frame_height

        self.region_manager = RegionManager(frame_width, frame_height)
        self.validator = EvidenceValidator()
        self.detector = AnonymousPersonDetector(confidence_threshold=0.28)
        self.tracker = AnonymousTracker(min_confirm_frames=2)
        self.checkout_monitor = CheckoutCongestionMonitor()
        self.shelf_monitor = ShelfVisualChangeMonitor()

        # Cached latest state for API responses
        self.latest_state: Dict[str, Any] = {}
        self.latest_annotated_frame: Optional[np.ndarray] = None
        self.audit_log: List[str] = []

    def process_frame(
        self,
        frame: Optional[np.ndarray],
        show_boxes: bool = True,
        show_regions: bool = True,
        apply_privacy_blur: bool = False,
    ) -> Tuple[Optional[np.ndarray], Dict[str, Any]]:
        """
        Executes the 4 independent features on the current video frame.
        """
        timestamp = time.time()

        # Handle empty/missing frame
        if frame is None or frame.size == 0:
            rel_report = self.validator.evaluate_reliability(None, [])
            payload = self._build_empty_payload(rel_report)
            self.latest_state = payload
            return None, payload

        # =========================================================
        # FEATURE 1: CAMERA-WIDE PEOPLE DETECTION & TRACKING
        # (Runs on the 100% full frame — never cropped by regions)
        # =========================================================
        raw_detections = self.detector.detect(frame)
        
        # =========================================================
        # FEATURE 4: VIDEO & ANALYTICS RELIABILITY MONITORING
        # =========================================================
        rel_report = self.validator.evaluate_reliability(frame, raw_detections)

        # Update anonymous tracker across whole camera frame
        active_tracks: List[Tracklet] = []
        if rel_report.is_operable:
            val_boxes = [d["bbox"] for d in raw_detections]
            val_confs = [d["confidence"] for d in raw_detections]
            active_tracks = self.tracker.update(val_boxes, val_confs, timestamp=timestamp)

        # Conservative camera-wide count formulation
        n_confirmed = len(active_tracks)
        if rel_report.people_reliability == "Reliable":
            people_display = f"{n_confirmed}"
            people_label = f"Estimated visible people: {n_confirmed}"
            people_badge_class = "High"
        elif rel_report.people_reliability == "Reduced":
            low, high = rel_report.suggested_count_range
            # Ground with actual confirmed tracks
            low = min(low, n_confirmed)
            high = max(high, n_confirmed)
            people_display = f"{low}–{high}" if low != high else f"{low}"
            people_label = f"Estimated visible people: {people_display}"
            people_badge_class = "Medium"
        else:
            people_display = "Unavailable"
            people_label = "People count unavailable — visual evidence degraded"
            people_badge_class = "Low"

        # =========================================================
        # FEATURE 2: USER-DEFINED CHECKOUT CONGESTION MONITORING
        # (Operates strictly on user-defined checkout polygon)
        # =========================================================
        checkout_report: CheckoutReport = self.checkout_monitor.evaluate(
            active_tracks=active_tracks,
            checkout_region=self.region_manager.checkout_region,
            video_quality_status=rel_report.video_quality.status.upper(),
        )

        # =========================================================
        # FEATURE 3: USER-DEFINED SHELF VISUAL-CHANGE MONITORING
        # (Operates strictly on user-defined shelf polygon with obstruction gate)
        # =========================================================
        shelf_report: ShelfReport = self.shelf_monitor.evaluate(
            frame=frame,
            active_tracks=active_tracks,
            shelf_region=self.region_manager.shelf_region,
            region_manager=self.region_manager,
            video_quality_status=rel_report.video_quality.status.upper(),
        )

        # =========================================================
        # AUDIT LOGGING ("Why this number?")
        # =========================================================
        audit_trail = [
            f"Frame Quality: {rel_report.video_quality.status} (Clarity: {rel_report.video_quality.blur_score:.1f}, Brightness: {rel_report.video_quality.brightness:.0f}/255)",
            f"Camera-Wide People Counting: {len(raw_detections)} candidates detected; {n_confirmed} confirmed tracks. Cluster overlap: {rel_report.occlusion_index*100:.0f}%.",
            f"Checkout Region: {checkout_report.explanation}",
            f"Shelf Monitor: {shelf_report.explanation}",
        ]
        if rel_report.video_quality.issues:
            audit_trail.append(f"Scene Warnings: {'; '.join(rel_report.video_quality.issues)}")

        self.audit_log = audit_trail

        # =========================================================
        # VISUAL ANNOTATION (Real detections and user regions only)
        # =========================================================
        annotated_frame = frame.copy()

        # Optional: Privacy blur filter
        if apply_privacy_blur and active_tracks:
            annotated_frame = AnonymousPersonDetector.apply_privacy_filter(
                annotated_frame, [t.bbox for t in active_tracks]
            )

        # Optional: User-defined region outlines
        if show_regions:
            self._draw_regions(annotated_frame, checkout_report, shelf_report)

        # Optional: Computer-vision bounding boxes
        if show_boxes and active_tracks:
            self._draw_detections(annotated_frame, active_tracks)

        # Compile final analytics payload
        analytics_payload = {
            "timestamp": timestamp,
            # Feature 1: Camera-Wide People Counting
            "people_count": {
                "display": people_display,
                "label": people_label,
                "confirmed_count": n_confirmed,
                "reliability": people_badge_class,
                "occlusion_index": rel_report.occlusion_index,
            },
            # Feature 2: Checkout Congestion
            "checkout": {
                "region_name": checkout_report.region_name,
                "status": checkout_report.status,
                "visible_people": checkout_report.visible_people_count,
                "is_congested": checkout_report.is_congested,
                "reliability": checkout_report.reliability,
                "dwell_duration": checkout_report.dwell_duration,
                "explanation": checkout_report.explanation,
            },
            # Feature 3: Shelf Visual Change
            "shelf": {
                "region_name": shelf_report.region_name,
                "status": shelf_report.status,
                "is_obstructed": shelf_report.is_obstructed,
                "is_changed": shelf_report.is_changed,
                "change_percentage": shelf_report.change_percentage,
                "reliability": shelf_report.reliability,
                "explanation": shelf_report.explanation,
            },
            # Feature 4: Video / Analytics Reliability
            "reliability": {
                "video_quality": rel_report.video_quality.status,
                "people_detection": rel_report.people_reliability,
                "checkout_analysis": rel_report.checkout_reliability,
                "shelf_analysis": (
                    "Temporarily obstructed" if shelf_report.is_obstructed
                    else rel_report.shelf_reliability
                ),
                "blur_score": rel_report.video_quality.blur_score,
                "brightness": rel_report.video_quality.brightness,
                "contrast": rel_report.video_quality.contrast,
                "issues": rel_report.video_quality.issues,
                "explanation": rel_report.video_quality.explanation,
            },
            "audit_trail": audit_trail,
        }

        self.latest_state = analytics_payload
        self.latest_annotated_frame = annotated_frame
        return annotated_frame, analytics_payload

    def _draw_regions(
        self,
        frame: np.ndarray,
        checkout_report: CheckoutReport,
        shelf_report: ShelfReport,
    ):
        """Draws user-defined regions on the video frame."""
        overlay = frame.copy()
        
        # Draw Checkout Region
        c_reg = self.region_manager.checkout_region
        if c_reg and len(c_reg.polygon) >= 3:
            pts = np.array(c_reg.polygon, dtype=np.int32)
            # Highlight if congested
            color = (0, 0, 255) if checkout_report.is_congested else c_reg.color_rgb
            cv2.polylines(overlay, [pts], True, color, 2, cv2.LINE_AA)
            lx, ly = c_reg.polygon[0]
            label = f"{c_reg.name.upper()} ({checkout_report.visible_people_count} people)"
            cv2.putText(overlay, label, (lx, max(18, ly - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.40, color, 1, cv2.LINE_AA)

        # Draw Shelf Region
        s_reg = self.region_manager.shelf_region
        if s_reg and len(s_reg.polygon) >= 3:
            pts = np.array(s_reg.polygon, dtype=np.int32)
            color = (0, 165, 255) if shelf_report.is_obstructed else s_reg.color_rgb
            cv2.polylines(overlay, [pts], True, color, 2, cv2.LINE_AA)
            lx, ly = s_reg.polygon[0]
            status_tag = " [OBSTRUCTED]" if shelf_report.is_obstructed else ""
            label = f"{s_reg.name.upper()}{status_tag}"
            cv2.putText(overlay, label, (lx, max(18, ly - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.40, color, 1, cv2.LINE_AA)

        cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)

    def _draw_detections(self, frame: np.ndarray, tracks: List[Tracklet]):
        """Draws bounding boxes strictly for confirmed computer vision detections."""
        for t in tracks:
            x, y, w, h = t.bbox
            color = (0, 220, 80) if t.confidence > 0.50 else (0, 190, 240)
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            
            label = f"Person #{t.track_id}"
            cv2.rectangle(frame, (x, max(0, y - 18)), (x + len(label) * 8 + 4, y), color, -1)
            cv2.putText(frame, label, (x + 3, max(12, y - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (15, 15, 15), 1, cv2.LINE_AA)

    def _build_empty_payload(self, rel_report: ReliabilityReport) -> Dict[str, Any]:
        return {
            "timestamp": time.time(),
            "people_count": {
                "display": "Unavailable",
                "label": "Video source unavailable",
                "confirmed_count": 0,
                "reliability": "Unavailable",
                "occlusion_index": 0.0,
            },
            "checkout": {
                "region_name": self.region_manager.checkout_region.name if self.region_manager.checkout_region else "Checkout",
                "status": "Video source unavailable",
                "visible_people": 0,
                "is_congested": False,
                "reliability": "Unavailable",
                "dwell_duration": 0.0,
                "explanation": "No video stream received.",
            },
            "shelf": {
                "region_name": self.region_manager.shelf_region.name if self.region_manager.shelf_region else "Shelf",
                "status": "Video source unavailable",
                "is_obstructed": False,
                "is_changed": False,
                "change_percentage": 0.0,
                "reliability": "Unavailable",
                "explanation": "No video stream received.",
            },
            "reliability": {
                "video_quality": "Unavailable",
                "people_detection": "Unavailable",
                "checkout_analysis": "Unavailable",
                "shelf_analysis": "Unavailable",
                "blur_score": 0.0,
                "brightness": 0.0,
                "contrast": 0.0,
                "issues": ["Video source unavailable"],
                "explanation": "No video frame received.",
            },
            "audit_trail": ["Video source disconnected or unavailable."],
        }
