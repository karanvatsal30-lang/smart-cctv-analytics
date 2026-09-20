"""
FEATURE 4: Video & Analytics Reliability Monitoring Engine.
Monitors whether video conditions are suitable for reliable computer vision:
- Camera disconnected / missing video -> "Video source unavailable"
- Very dark image -> "Insufficient visual evidence — frame too dark"
- Excessive blur -> "Excessive blur detected — analytics reliability reduced"
- Severe glare / overexposure -> "Severe glare detected"
- Heavy crowd occlusion -> "People count unreliable — heavy occlusion"
- Emits individual reliability statuses for each feature.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional
import numpy as np
import cv2

@dataclass
class VideoQuality:
    score: float          # 0.0 to 1.0
    status: str           # "Good", "Degraded", "Unavailable"
    blur_score: float
    brightness: float
    contrast: float
    issues: List[str] = field(default_factory=list)
    explanation: str = "Video quality suitable for analytics"

@dataclass
class ReliabilityReport:
    video_quality: VideoQuality
    people_reliability: str     # "Reliable", "Reduced", "Unreliable"
    checkout_reliability: str   # "Reliable", "Reduced", "Unavailable"
    shelf_reliability: str      # "Reliable", "Reduced", "Unavailable"
    occlusion_index: float
    suggested_count_range: Tuple[int, int]
    is_operable: bool


class EvidenceValidator:
    def __init__(
        self,
        min_blur_var: float = 35.0,
        min_brightness: float = 28.0,
        max_brightness: float = 230.0,
        min_contrast: float = 20.0,
    ):
        self.min_blur_var = min_blur_var
        self.min_brightness = min_brightness
        self.max_brightness = max_brightness
        self.min_contrast = min_contrast

    def evaluate_video_quality(self, frame: Optional[np.ndarray]) -> VideoQuality:
        """Evaluates video frame clarity, contrast, and illumination."""
        if frame is None or frame.size == 0:
            return VideoQuality(
                score=0.0,
                status="Unavailable",
                blur_score=0.0,
                brightness=0.0,
                contrast=0.0,
                issues=["Video source unavailable or disconnected"],
                explanation="No video frame received.",
            )

        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame

        # 1. Blur / Lens Obstruction
        laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        
        # 2. Brightness & Contrast
        mean_brightness = float(np.mean(gray))
        contrast_std = float(np.std(gray))

        issues = []
        clarity_penalty = 0.0

        if laplacian_var < self.min_blur_var:
            issues.append(f"Excessive visual blur (Clarity score: {laplacian_var:.1f})")
            clarity_penalty += 0.35

        if mean_brightness < self.min_brightness:
            issues.append(f"Scene very dark ({mean_brightness:.0f}/255)")
            clarity_penalty += 0.50
        elif mean_brightness > self.max_brightness:
            issues.append(f"Severe camera glare / overexposure ({mean_brightness:.0f}/255)")
            clarity_penalty += 0.40

        if contrast_std < self.min_contrast:
            issues.append(f"Low contrast / washed out image ({contrast_std:.1f})")
            clarity_penalty += 0.25

        score = max(0.0, min(1.0, 1.0 - clarity_penalty))

        if score >= 0.70:
            status = "Good"
            explanation = "Video quality good; clear visibility"
        elif score >= 0.35:
            status = "Degraded"
            explanation = "Video quality degraded; analytics reliability reduced"
        else:
            status = "Unavailable"
            explanation = "Insufficient visual evidence — frame too degraded"

        return VideoQuality(
            score=round(score, 2),
            status=status,
            blur_score=round(laplacian_var, 1),
            brightness=round(mean_brightness, 1),
            contrast=round(contrast_std, 1),
            issues=issues,
            explanation=explanation,
        )

    def compute_iou(self, boxA: Tuple[int, int, int, int], boxB: Tuple[int, int, int, int]) -> float:
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[0] + boxA[2], boxB[0] + boxB[2])
        yB = min(boxA[1] + boxA[3], boxB[1] + boxB[3])

        interArea = max(0, xB - xA) * max(0, yB - yA)
        boxAArea = boxA[2] * boxA[3]
        boxBArea = boxB[2] * boxB[3]
        unionArea = float(boxAArea + boxBArea - interArea)

        if unionArea <= 0:
            return 0.0
        return interArea / unionArea

    def evaluate_reliability(
        self,
        frame: Optional[np.ndarray],
        raw_detections: List[Dict[str, Any]],
    ) -> ReliabilityReport:
        """
        Evaluates overall scene and feature-level reliability.
        Calculates occlusion index and suggested conservative count ranges.
        """
        vq = self.evaluate_video_quality(frame)

        if vq.status == "Unavailable":
            return ReliabilityReport(
                video_quality=vq,
                people_reliability="Unreliable",
                checkout_reliability="Unavailable",
                shelf_reliability="Unavailable",
                occlusion_index=0.0,
                suggested_count_range=(0, 0),
                is_operable=False,
            )

        # Occlusion analysis between detected people
        n_dets = len(raw_detections)
        occlusion_pairs = 0
        total_pairs = max(1, (n_dets * (n_dets - 1)) // 2)

        for i in range(n_dets):
            for j in range(i + 1, n_dets):
                iou = self.compute_iou(raw_detections[i]["bbox"], raw_detections[j]["bbox"])
                if iou > 0.25:
                    occlusion_pairs += 1

        occlusion_index = round(occlusion_pairs / total_pairs, 2) if n_dets > 1 else 0.0

        # Determine conservative count range
        if vq.status == "Good" and occlusion_index < 0.25:
            people_rel = "Reliable"
            count_range = (n_dets, n_dets)
        elif vq.status in ("Good", "Degraded") and occlusion_index < 0.45:
            people_rel = "Reduced"
            count_range = (n_dets, n_dets + 1)
        elif occlusion_index >= 0.45 or vq.status == "Degraded":
            people_rel = "Reduced"
            lower = max(0, n_dets - 1)
            upper = n_dets + max(1, int(n_dets * 0.35))
            count_range = (lower, upper)
        else:
            people_rel = "Unreliable"
            count_range = (0, 0)

        checkout_rel = "Reliable" if vq.status == "Good" else "Reduced"
        shelf_rel = "Reliable" if vq.status == "Good" else "Reduced"

        return ReliabilityReport(
            video_quality=vq,
            people_reliability=people_rel,
            checkout_reliability=checkout_rel,
            shelf_reliability=shelf_rel,
            occlusion_index=occlusion_index,
            suggested_count_range=count_range,
            is_operable=True,
        )
