"""
Scale-Adaptive Multi-Object Spatial Tracker.
Maintains persistent anonymous tracklets across frames for store CCTV analytics.
Key Features:
- Distance matching threshold scales adaptively with person distance/size
- Completely anonymous IDs (Track #1, Track #2)
- Zero biometric features, zero facial embeddings
- Temporal confirmation: requires >= min_confirm_frames to graduate to VALIDATED
- Cleaned: Heatmap buffers removed per user request
"""

import time
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional
import numpy as np

@dataclass
class Tracklet:
    track_id: int
    bbox: Tuple[int, int, int, int]  # (x, y, w, h)
    centroid: Tuple[int, int]         # (cx, cy)
    foot_point: Tuple[int, int]       # (cx, y + h) - floor contact point
    confidence: float
    first_seen: float
    last_seen: float
    history: List[Tuple[int, int]] = field(default_factory=list)  # [(cx, cy), ...]
    hit_streak: int = 1
    lost_frames: int = 0
    is_confirmed: bool = False
    current_zone: Optional[str] = None

    @property
    def total_dwell_seconds(self) -> float:
        return max(0.0, self.last_seen - self.first_seen)


class AnonymousTracker:
    def __init__(
        self,
        max_lost_frames: int = 15,
        min_confirm_frames: int = 2,
    ):
        self.next_track_id = 1
        self.tracks: Dict[int, Tracklet] = {}
        self.max_lost_frames = max_lost_frames
        self.min_confirm_frames = min_confirm_frames

    def _centroid(self, bbox: Tuple[int, int, int, int]) -> Tuple[int, int]:
        x, y, w, h = bbox
        return (int(x + w / 2), int(y + h / 2))

    def _foot_point(self, bbox: Tuple[int, int, int, int]) -> Tuple[int, int]:
        x, y, w, h = bbox
        return (int(x + w / 2), int(y + h))

    def update(
        self,
        validated_boxes: List[Tuple[int, int, int, int]],
        confidences: List[float],
        timestamp: Optional[float] = None,
    ) -> List[Tracklet]:
        """
        Updates active tracks with newly validated detections.
        Uses scale-adaptive distance matching based on bounding box height.
        Returns list of currently confirmed, active tracks.
        """
        if timestamp is None:
            timestamp = time.time()

        det_centroids = [self._centroid(b) for b in validated_boxes]
        det_feet = [self._foot_point(b) for b in validated_boxes]

        track_ids = list(self.tracks.keys())
        matched_tracks = set()
        matched_detections = set()

        if track_ids and det_centroids:
            # Build cost matrix
            cost_matrix = np.zeros((len(track_ids), len(det_centroids)), dtype=np.float32)
            for i, tid in enumerate(track_ids):
                t_centroid = self.tracks[tid].centroid
                for j, d_centroid in enumerate(det_centroids):
                    dist = math.hypot(t_centroid[0] - d_centroid[0], t_centroid[1] - d_centroid[1])
                    cost_matrix[i, j] = dist

            # Greedy matching with scale-adaptive distance threshold
            rows, cols = np.unravel_index(np.argsort(cost_matrix, axis=None), cost_matrix.shape)
            for r, c in zip(rows, cols):
                if r in matched_tracks or c in matched_detections:
                    continue
                
                tid = track_ids[r]
                track_h = self.tracks[tid].bbox[3]
                det_h = validated_boxes[c][3]
                avg_h = (track_h + det_h) / 2.0
                
                # Dynamic threshold: distant/small people have smaller motion bounds
                # Near/large people have larger motion bounds (35px to 130px)
                adaptive_thresh = max(35.0, min(130.0, avg_h * 0.85))

                if cost_matrix[r, c] <= adaptive_thresh:
                    matched_tracks.add(r)
                    matched_detections.add(c)

                    t = self.tracks[tid]
                    t.bbox = validated_boxes[c]
                    t.centroid = det_centroids[c]
                    t.foot_point = det_feet[c]
                    t.confidence = confidences[c] if c < len(confidences) else 0.5
                    t.last_seen = timestamp
                    t.history.append(t.centroid)
                    t.hit_streak += 1
                    t.lost_frames = 0

                    if t.hit_streak >= self.min_confirm_frames:
                        t.is_confirmed = True

        # Unmatched detections -> spawn candidate tracks
        for j in range(len(validated_boxes)):
            if j not in matched_detections:
                new_track = Tracklet(
                    track_id=self.next_track_id,
                    bbox=validated_boxes[j],
                    centroid=det_centroids[j],
                    foot_point=det_feet[j],
                    confidence=confidences[j] if j < len(confidences) else 0.5,
                    first_seen=timestamp,
                    last_seen=timestamp,
                    history=[det_centroids[j]],
                    hit_streak=1,
                    lost_frames=0,
                    is_confirmed=(self.min_confirm_frames <= 1),
                )
                self.tracks[self.next_track_id] = new_track
                self.next_track_id += 1

        # Unmatched tracks -> increment lost counter
        active_track_ids = list(self.tracks.keys())
        for tid in active_track_ids:
            if tid in [track_ids[r] for r in matched_tracks]:
                continue
            self.tracks[tid].lost_frames += 1
            if self.tracks[tid].lost_frames > self.max_lost_frames:
                del self.tracks[tid]

        return [t for t in self.tracks.values() if t.is_confirmed]
