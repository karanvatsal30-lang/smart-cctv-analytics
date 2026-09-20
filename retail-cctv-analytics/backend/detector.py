"""
Deep Learning Anonymous Person Detector (YOLOv8 via OpenCV DNN).
Implements privacy-preserving person detection across all camera distances & angles.
Rules:
- NO facial recognition
- NO age, gender, emotion, or biometric profiling
- NO suspicion or threat classification
- Accurate multi-scale detection (foreground, background, oblique, ceiling angles)
- Real-time privacy blurring filter
"""

import os
import cv2
import numpy as np
from typing import List, Dict, Any, Tuple

class AnonymousPersonDetector:
    def __init__(self, confidence_threshold: float = 0.28, model_path: str = "models/yolov8n.onnx"):
        self.confidence_threshold = confidence_threshold
        self.net = None
        self.use_yolo = False
        self.detector_name = "YOLOv8n Neural Person Detector (OpenCV DNN)"

        # Check for model file
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        abs_model_path = os.path.join(base_dir, model_path)
        if not os.path.exists(abs_model_path):
            # Try direct relative path
            abs_model_path = model_path

        if os.path.exists(abs_model_path):
            try:
                self.net = cv2.dnn.readNetFromONNX(abs_model_path)
                # Set OpenCV DNN backend & target to CPU
                self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
                self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
                self.use_yolo = True
            except Exception as e:
                print(f"[Detector] Warning: Could not load YOLO ONNX model ({e}). Using adaptive fallback.")
                self.use_yolo = False

        # Fallback adaptive foreground subtractor
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=300,
            varThreshold=24,
            detectShadows=True
        )

    def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detects visible human silhouettes in a video frame.
        Uses YOLOv8 person detection (COCO class 0).
        Accurately captures people near, far, at oblique angles, and in groups.
        """
        if frame is None or frame.size == 0:
            return []

        orig_h, orig_w = frame.shape[:2]

        if self.use_yolo and self.net is not None:
            return self._detect_yolo(frame, orig_w, orig_h)
        else:
            return self._detect_fallback(frame, orig_w, orig_h)

    def _detect_yolo(self, frame: np.ndarray, orig_w: int, orig_h: int) -> List[Dict[str, Any]]:
        # YOLOv8 input normalization: 640x640, RGB, scale 1/255.0
        blob = cv2.dnn.blobFromImage(frame, 1.0 / 255.0, (640, 640), swapRB=True, crop=False)
        self.net.setInput(blob)
        preds = self.net.forward()

        # Output shape: (1, 84, 8400) -> transpose to (8400, 84)
        preds = np.squeeze(preds)
        preds = np.transpose(preds)

        boxes = []
        confidences = []

        # Class index 0 is 'person' in COCO dataset
        person_scores = preds[:, 4]
        candidate_indices = np.where(person_scores >= self.confidence_threshold)[0]

        scale_x = orig_w / 640.0
        scale_y = orig_h / 640.0

        for idx in candidate_indices:
            score = float(person_scores[idx])
            row = preds[idx]
            cx, cy, w, h = row[0], row[1], row[2], row[3]

            # Convert center (cx, cy, w, h) to top-left (x, y, w, h)
            left = int((cx - w / 2.0) * scale_x)
            top = int((cy - h / 2.0) * scale_y)
            width = int(w * scale_x)
            height = int(h * scale_y)

            # Clamp boundaries
            left = max(0, min(orig_w - 1, left))
            top = max(0, min(orig_h - 1, top))
            width = max(1, min(orig_w - left, width))
            height = max(1, min(orig_h - top, height))

            # Minimum size threshold (disregard sub-15px noise)
            if height >= 20 and width >= 10:
                boxes.append([left, top, width, height])
                confidences.append(score)

        # Apply Non-Maximum Suppression to eliminate overlapping boxes
        detections = []
        if boxes:
            indices = cv2.dnn.NMSBoxes(
                bboxes=boxes,
                scores=confidences,
                score_threshold=float(self.confidence_threshold),
                nms_threshold=0.45
            )

            if len(indices) > 0:
                for i in indices.flatten():
                    bx, by, bw, bh = boxes[i]
                    detections.append({
                        "bbox": (bx, by, bw, bh),
                        "confidence": round(confidences[i], 2),
                    })

        return detections

    def _detect_fallback(self, frame: np.ndarray, orig_w: int, orig_h: int) -> List[Dict[str, Any]]:
        """Fallback foreground silhouette detector if ONNX weights are missing."""
        fg_mask = self.bg_subtractor.apply(frame)
        _, thresh = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        cleaned = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        detections = []

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 500:
                continue

            x, y, w, h = cv2.boundingRect(cnt)
            if h < 35 or (w / float(h)) > 2.0:
                continue

            hull = cv2.convexHull(cnt)
            solidity = float(area) / max(1.0, cv2.contourArea(hull))
            if solidity < 0.20:
                continue

            conf = min(0.90, max(0.35, 0.40 + (solidity * 0.40)))
            detections.append({
                "bbox": (x, y, w, h),
                "confidence": round(conf, 2),
            })

        return detections

    @staticmethod
    def apply_privacy_filter(frame: np.ndarray, bboxes: List[Tuple[int, int, int, int]]) -> np.ndarray:
        """
        Applies a privacy-preserving blur to the head/face region of visible people.
        Ensures strict visual anonymity without capturing biometrics.
        """
        if frame is None or not bboxes:
            return frame

        anonymized = frame.copy()
        H, W = frame.shape[:2]

        for (x, y, w, h) in bboxes:
            head_h = max(8, int(h * 0.32))
            head_w = max(8, int(w * 0.70))
            head_x = x + int((w - head_w) / 2)
            head_y = y

            hx1 = max(0, min(W - 1, head_x))
            hy1 = max(0, min(H - 1, head_y))
            hx2 = max(0, min(W, head_x + head_w))
            hy2 = max(0, min(H, head_y + head_h))

            if hx2 > hx1 and hy2 > hy1:
                sub_face = anonymized[hy1:hy2, hx1:hx2]
                ksize = max(11, (hx2 - hx1) // 2 * 2 + 1)
                blurred = cv2.GaussianBlur(sub_face, (ksize, ksize), 30)
                anonymized[hy1:hy2, hx1:hx2] = blurred

        return anonymized
