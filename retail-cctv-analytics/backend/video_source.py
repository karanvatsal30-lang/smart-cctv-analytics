"""
Video Ingestion & Hardware Interface Diagnostics Engine.
Supports:
1. Synthetic Retail Benchmark Generator (instant out-of-the-box demoing)
2. Local Video Files (MP4, AVI)
3. Live Webcam
4. RTSP / IP Stream feeds
Includes explicit diagnostics when a stream lacks an accessible interface.
"""

import time
import os
import cv2
import numpy as np
from typing import Optional, Tuple, Dict, Any

class VideoSource:
    def __init__(self):
        self.cap: Optional[cv2.VideoCapture] = None
        self.source_type: str = "BENCHMARK"  # "BENCHMARK", "FILE", "WEBCAM", "RTSP"
        self.source_uri: str = "synthetic_retail_benchmark"
        self.is_running: bool = False
        self.status_message: str = "Initializing video stream..."
        self.connection_error: Optional[str] = None
        self.frame_count: int = 0
        self.fps_target: float = 20.0
        self.last_frame_time: float = 0.0
        self.actual_fps: float = 0.0
        self.frame_width: int = 640
        self.frame_height: int = 480

        # Benchmark simulation state
        self.sim_tick: int = 0
        self.shelf_empty_sim: bool = False  # Toggleable shelf depletion in simulation

    def open_benchmark(self):
        """Starts the built-in realistic retail simulation stream."""
        if self.cap is not None:
            self.cap.release()
            self.cap = None

        self.source_type = "BENCHMARK"
        self.source_uri = "Built-in Retail Simulation"
        self.is_running = True
        self.connection_error = None
        self.status_message = "Active (Built-in Retail Store CCTV Simulation)"
        self.sim_tick = 0

    def open_file(self, file_path: str) -> bool:
        """Opens a local video file (MP4, AVI)."""
        if not os.path.exists(file_path):
            self.connection_error = f"Video file not found at path: {file_path}"
            self.status_message = "Cannot access video file"
            return False

        if self.cap is not None:
            self.cap.release()

        self.cap = cv2.VideoCapture(file_path)
        if not self.cap.isOpened():
            self.connection_error = (
                f"Failed to decode video file '{os.path.basename(file_path)}'. "
                "Ensure standard H.264 / MP4 encoding."
            )
            self.status_message = "Cannot decode video file"
            return False

        self.source_type = "FILE"
        self.source_uri = file_path
        self.is_running = True
        self.connection_error = None
        self.status_message = f"Active (File: {os.path.basename(file_path)})"
        return True

    def open_webcam(self, device_index: int = 0) -> bool:
        """Opens a local camera device (USB or integrated webcam)."""
        if self.cap is not None:
            self.cap.release()

        self.cap = cv2.VideoCapture(device_index)
        if not self.cap.isOpened():
            self.connection_error = (
                f"Cannot open webcam device (Index {device_index}). "
                "Camera may be in use by another application or permissions are restricted."
            )
            self.status_message = "Webcam unavailable"
            return False

        self.source_type = "WEBCAM"
        self.source_uri = f"Webcam Device #{device_index}"
        self.is_running = True
        self.connection_error = None
        self.status_message = f"Active (Webcam #{device_index})"
        return True

    def open_rtsp(self, rtsp_url: str) -> bool:
        """
        Connects to an RTSP/IP camera video stream.
        Enforces clear failure messaging if CCTV does not expose an accessible stream.
        """
        if self.cap is not None:
            self.cap.release()

        # Attempt connection
        self.cap = cv2.VideoCapture(rtsp_url)
        if not self.cap.isOpened():
            self.connection_error = (
                "Cannot connect to video stream without an accessible RTSP/HTTP/ONVIF interface. "
                "Please verify network accessibility, camera IP, and stream authentication credentials. "
                "Legacy proprietary DVR systems require an accessible RTSP re-streamer or bridge."
            )
            self.status_message = "Stream connection failed"
            self.is_running = False
            return False

        self.source_type = "RTSP"
        self.source_uri = rtsp_url
        self.is_running = True
        self.connection_error = None
        self.status_message = f"Active (IP Stream: {rtsp_url})"
        return True

    def toggle_shelf_depletion_simulation(self):
        """Allows user to test shelf depletion detection in the benchmark feed."""
        self.shelf_empty_sim = not self.shelf_empty_sim

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Reads the next frame from the current source with FPS pacing."""
        now = time.time()
        elapsed = now - self.last_frame_time
        target_interval = 1.0 / self.fps_target

        if elapsed < target_interval:
            time.sleep(target_interval - elapsed)

        self.actual_fps = round(1.0 / max(0.001, time.time() - self.last_frame_time), 1)
        self.last_frame_time = time.time()

        if self.source_type == "BENCHMARK":
            frame = self._render_benchmark_frame()
            self.frame_count += 1
            return True, frame

        if self.cap is None or not self.cap.isOpened():
            return False, None

        ret, frame = self.cap.read()
        if not ret:
            # If video file reached the end, loop it
            if self.source_type == "FILE":
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()

        if ret and frame is not None:
            self.frame_count += 1
            # Standardize resolution for consistent computer vision processing
            if frame.shape[1] != self.frame_width or frame.shape[0] != self.frame_height:
                frame = cv2.resize(frame, (self.frame_width, self.frame_height))
            return True, frame

        return False, None

    def _render_benchmark_frame(self) -> np.ndarray:
        """
        Renders an ultra-realistic retail CCTV camera perspective including:
        - Store floor tiles with realistic perspective lines
        - Shelf Bay A with textured product packaging (or bare depleted shelf when toggled)
        - Customer Assistance Desk with counter
        - Checkout lane with conveyer belt
        - Dynamically moving shoppers (walking to shelf, dwelling at service desk, queueing)
        """
        W, H = self.frame_width, self.frame_height
        self.sim_tick += 1
        t = self.sim_tick / 20.0  # seconds

        frame = np.full((H, W, 3), (225, 228, 230), dtype=np.uint8)

        # 1. Perspective store floor tiles
        for row in range(int(H * 0.35), H, 35):
            cv2.line(frame, (0, row), (W, row), (200, 205, 210), 1)
        for col in range(0, W, 50):
            cv2.line(frame, (col, int(H * 0.35)), (int(col * 1.2 - 60), H), (205, 210, 215), 1)

        # 2. Store Back Wall
        cv2.rectangle(frame, (0, 0), (W, int(H * 0.35)), (240, 242, 245), -1)
        cv2.line(frame, (0, int(H * 0.35)), (W, int(H * 0.35)), (180, 185, 190), 2)

        # 3. Shelf Bay A (X: 15 to 185, Y: 75 to 290)
        sx1, sy1, sx2, sy2 = 15, 75, 185, 290
        # Shelf Frame
        cv2.rectangle(frame, (sx1, sy1), (sx2, sy2), (80, 90, 95), -1)
        cv2.rectangle(frame, (sx1, sy1), (sx2, sy2), (40, 45, 50), 2)

        if not self.shelf_empty_sim:
            # Render Stocked Products on 3 Shelf tiers
            tier_height = (sy2 - sy1) // 3
            for tier in range(3):
                ty1 = sy1 + tier * tier_height + 8
                ty2 = ty1 + tier_height - 12
                # Shelf rack divider
                cv2.line(frame, (sx1, ty2 + 4), (sx2, ty2 + 4), (200, 200, 200), 2)
                # Draw colorful product boxes/bottles
                for px in range(sx1 + 6, sx2 - 20, 16):
                    color = ((px * 37) % 200 + 40, (px * 83) % 180 + 50, (px * 131) % 220 + 35)
                    cv2.rectangle(frame, (px, ty1), (px + 12, ty2), color, -1)
                    cv2.rectangle(frame, (px, ty1), (px + 12, ty2), (30, 30, 30), 1)
        else:
            # Depleted/Empty shelf: bare metal back-panel with empty wire racks
            tier_height = (sy2 - sy1) // 3
            cv2.rectangle(frame, (sx1 + 4, sy1 + 4), (sx2 - 4, sy2 - 4), (110, 115, 120), -1)
            for tier in range(3):
                ty = sy1 + (tier + 1) * tier_height - 6
                cv2.line(frame, (sx1 + 4, ty), (sx2 - 4, ty), (160, 165, 170), 2)
                # Draw small wire rack lines
                for wx in range(sx1 + 10, sx2 - 10, 12):
                    cv2.line(frame, (wx, ty), (wx, ty + 5), (140, 145, 150), 1)

        # 4. Customer Service Assistance Desk (X: 260 to 445, Y: 50 to 215)
        cx1, cy1, cx2, cy2 = 260, 50, 445, 215
        # Service Counter
        cv2.rectangle(frame, (cx1 + 10, cy1 + 70), (cx2 - 10, cy2), (65, 105, 150), -1)
        cv2.rectangle(frame, (cx1 + 10, cy1 + 70), (cx2 - 10, cy2), (35, 60, 90), 2)
        cv2.rectangle(frame, (cx1, cy1 + 60), (cx2, cy1 + 75), (200, 205, 215), -1)
        # Signboard
        cv2.putText(frame, "SERVICE DESK", (cx1 + 25, cy1 + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (60, 70, 80), 1)

        # 5. Checkout Conveyor Belt & Station (X: 420 to 605, Y: 270 to 455)
        kx1, ky1, kx2, ky2 = 420, 270, 605, 455
        cv2.rectangle(frame, (kx1, ky1), (kx2, ky2), (90, 95, 100), -1)
        cv2.line(frame, (kx1 + 20, ky1 + 40), (kx2 - 20, ky1 + 40), (40, 40, 40), 12)
        cv2.putText(frame, "CHECKOUT 1", (kx1 + 30, ky1 + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (230, 230, 230), 1)

        # 6. Simulated Shoppers / Pedestrians with realistic movement profiles
        # Shopper 1: Enters, walks to Shelf A, browses
        s1_phase = (t * 0.25) % 4.0
        if s1_phase < 1.0:
            # Walking towards shelf
            s1_x = int(60 + s1_phase * 60)
            s1_y = int(380 - s1_phase * 170)
        elif s1_phase < 2.5:
            # Dwelling near shelf
            s1_x = int(120 + np.sin(t * 1.5) * 6)
            s1_y = int(210 + np.cos(t * 1.5) * 4)
        else:
            # Walking to checkout
            p = (s1_phase - 2.5) / 1.5
            s1_x = int(120 + p * 340)
            s1_y = int(210 + p * 120)
        self._draw_humanoid(frame, s1_x, s1_y, height=85, shirt_color=(180, 50, 50))

        # Shopper 2: Dwells at Customer Service Desk (triggers unattended check!)
        # Stays at service desk from t=5s to t=45s
        s2_cycle = t % 60.0
        if s2_cycle < 5.0:
            # Approaching service desk
            p = s2_cycle / 5.0
            s2_x = int(180 + p * 140)
            s2_y = int(320 - p * 120)
        elif s2_cycle < 48.0:
            # Lingering / waiting at service desk
            s2_x = int(320 + np.sin(t * 0.8) * 3)
            s2_y = int(200 + np.cos(t * 0.8) * 2)
        else:
            # Leaving
            p = (s2_cycle - 48.0) / 12.0
            s2_x = int(320 - p * 200)
            s2_y = int(200 + p * 180)
        self._draw_humanoid(frame, s2_x, s2_y, height=82, shirt_color=(40, 120, 180))

        # Shopper 3: In checkout queue
        s3_x = int(480 + np.sin(t * 0.5) * 4)
        s3_y = int(340 + np.cos(t * 0.5) * 3)
        self._draw_humanoid(frame, s3_x, s3_y, height=80, shirt_color=(60, 160, 60))

        # Timestamp watermark in top-left
        time_str = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, f"CCTV 01 - RETAIL MAIN | {time_str}", (15, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (30, 30, 30), 1, cv2.LINE_AA)

        return frame

    def _draw_humanoid(self, frame: np.ndarray, x: int, y: int, height: int = 80, shirt_color=(120, 120, 120)):
        """Draws an anatomically proportioned human figure for the simulation."""
        H, W = frame.shape[:2]
        w = int(height * 0.42)
        # Bounding limits
        top_y = y - height
        if top_y < 5 or (x + w) >= W - 5 or y >= H - 5 or x < 5:
            return

        head_radius = int(height * 0.12)
        head_cx = x + w // 2
        head_cy = top_y + head_radius

        # Head (anonymized silhouette)
        cv2.circle(frame, (head_cx, head_cy), head_radius, (190, 175, 160), -1)
        cv2.circle(frame, (head_cx, head_cy), head_radius, (70, 65, 60), 1)

        # Torso
        torso_top = head_cy + head_radius
        torso_bot = top_y + int(height * 0.62)
        cv2.rectangle(frame, (x + 4, torso_top), (x + w - 4, torso_bot), shirt_color, -1)
        cv2.rectangle(frame, (x + 4, torso_top), (x + w - 4, torso_bot), (30, 30, 30), 1)

        # Legs
        leg_mid = x + w // 2
        leg_w = max(4, (w - 10) // 2)
        leg_bot = y
        # Left leg
        cv2.rectangle(frame, (x + 5, torso_bot), (x + 5 + leg_w, leg_bot), (60, 60, 70), -1)
        # Right leg
        cv2.rectangle(frame, (x + w - 5 - leg_w, torso_bot), (x + w - 5, leg_bot), (60, 60, 70), -1)

    def get_status(self) -> Dict[str, Any]:
        """Returns hardware and interface connection diagnostics."""
        return {
            "source_type": self.source_type,
            "source_uri": self.source_uri,
            "is_running": self.is_running,
            "status_message": self.status_message,
            "connection_error": self.connection_error,
            "actual_fps": self.actual_fps,
            "frame_count": self.frame_count,
            "shelf_depleted_sim": self.shelf_empty_sim,
        }

    def release(self):
        """Releases active video capture."""
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.is_running = False
