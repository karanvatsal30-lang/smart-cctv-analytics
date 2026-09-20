"""
FEATURE 2: User-Defined Checkout Congestion Monitoring.
Rules:
- Does NOT assume checkout counter position; operates strictly inside user-defined region.
- Completely separate from camera-wide people counting.
- Neutral terminology: "Visible people in checkout region".
- Looks for persistent presence over time before indicating possible congestion.
- Never guesses if visibility is poor: "Unable to reliably assess checkout area".
"""

import time
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from .regions import RegionManager, UserRegion

@dataclass
class CheckoutReport:
    region_name: str
    visible_people_count: int
    is_congested: bool
    status: str           # "Normal", "Possible checkout congestion", "Unable to reliably assess checkout area"
    reliability: str      # "High", "Medium", "Low", "Unavailable"
    dwell_duration: float # Seconds congestion has persisted
    explanation: str

class CheckoutCongestionMonitor:
    def __init__(
        self,
        congestion_threshold_people: int = 3,
        congestion_persistence_seconds: float = 6.0,
    ):
        self.congestion_threshold_people = congestion_threshold_people
        self.congestion_persistence_seconds = congestion_persistence_seconds
        self.congestion_start_time: Optional[float] = None
        self.consecutive_congested_frames: int = 0

    def evaluate(
        self,
        active_tracks: List[Any],
        checkout_region: Optional[UserRegion],
        video_quality_status: str = "HIGH",
    ) -> CheckoutReport:
        """
        Evaluates people appearing inside the user-defined checkout polygon.
        """
        region_name = checkout_region.name if checkout_region else "Checkout Area"

        if checkout_region is None or not checkout_region.polygon or len(checkout_region.polygon) < 3:
            return CheckoutReport(
                region_name=region_name,
                visible_people_count=0,
                is_congested=False,
                status="No checkout region configured",
                reliability="Unavailable",
                dwell_duration=0.0,
                explanation="Draw a checkout monitoring region in settings to activate this feature.",
            )

        # Environmental quality check
        if video_quality_status in ("UNAVAILABLE", "LOW"):
            self.congestion_start_time = None
            return CheckoutReport(
                region_name=region_name,
                visible_people_count=0,
                is_congested=False,
                status="Unable to reliably assess checkout area",
                reliability="Low",
                dwell_duration=0.0,
                explanation="Camera visibility degraded (blur, low light, or severe occlusion).",
            )

        # Count visible people whose contact/foot point or centroid falls inside the checkout region
        now = time.time()
        people_in_checkout = 0
        for track in active_tracks:
            # Check foot point or centroid
            in_poly = (
                RegionManager.point_in_polygon(track.foot_point, checkout_region.polygon) or
                RegionManager.point_in_polygon(track.centroid, checkout_region.polygon)
            )
            if in_poly:
                people_in_checkout += 1

        # Temporal persistence check
        is_above_threshold = (people_in_checkout >= self.congestion_threshold_people)

        if is_above_threshold:
            if self.congestion_start_time is None:
                self.congestion_start_time = now
            dwell_s = now - self.congestion_start_time
            self.consecutive_congested_frames += 1
        else:
            self.congestion_start_time = None
            self.consecutive_congested_frames = 0
            dwell_s = 0.0

        # Assess congestion status
        is_persistent = (dwell_s >= self.congestion_persistence_seconds)

        if is_persistent:
            status = "Possible checkout congestion"
            reliability = "High" if video_quality_status == "HIGH" else "Medium"
            explanation = (
                f"{people_in_checkout} visible people observed in {region_name} "
                f"persisting for {dwell_s:.0f}s."
            )
        elif is_above_threshold:
            status = "Monitoring cluster"
            reliability = "Medium"
            explanation = (
                f"{people_in_checkout} people in {region_name}; observing for persistence "
                f"({dwell_s:.0f}s / {self.congestion_persistence_seconds:.0f}s required)."
            )
        else:
            status = "Normal"
            reliability = "High" if video_quality_status == "HIGH" else "Medium"
            explanation = f"Visible people in {region_name}: {people_in_checkout}."

        return CheckoutReport(
            region_name=region_name,
            visible_people_count=people_in_checkout,
            is_congested=is_persistent,
            status=status,
            reliability=reliability,
            dwell_duration=round(dwell_s, 1),
            explanation=explanation,
        )
