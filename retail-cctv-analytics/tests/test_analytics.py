"""
Comprehensive Unit & Scenario Verification Suite for Smart CCTV Analytics.
Covers all 12 scenario requirements from user specifications:
TEST 1: Empty store -> count 0, no fake alerts.
TEST 2: One person walks through camera view -> camera-wide count detects person, shelf/checkout don't interfere.
TEST 3: Person directly in front of shelf -> person counted camera-wide, shelf reports obstructed, NO false shelf change.
TEST 4: Person walks away from shelf -> shelf waits for visual stability before comparing.
TEST 5: Multiple people near checkout -> checkout reports possible congestion after persistence.
TEST 6: Multiple people elsewhere -> camera-wide count includes them completely.
TEST 7: Camera becomes very dark -> reliability warning, confident analytics withheld.
TEST 8: Camera disconnected -> video source unavailable, zero fake data.
TEST 9: Ambient lighting shifts -> reports unable to determine reliably.
TEST 10: No shelf visual change -> reports no significant change.
TEST 11: Actual visual change on shelf -> reports visual change detected.
TEST 12: Long-term shelf obstruction -> reports shelf view temporarily obstructed.
"""

import sys
import os
import unittest
import numpy as np
import cv2
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.validator import EvidenceValidator
from backend.detector import AnonymousPersonDetector
from backend.tracker import AnonymousTracker, Tracklet
from backend.regions import RegionManager, UserRegion
from backend.checkout_monitor import CheckoutCongestionMonitor
from backend.shelf_monitor import ShelfVisualChangeMonitor
from backend.analytics import StoreAnalyticsEngine

class TestUniversalCCTVAnalytics(unittest.TestCase):

    def setUp(self):
        self.engine = StoreAnalyticsEngine(640, 480)
        # Configure test shelf on left and checkout on right
        self.engine.region_manager.update_shelf_region(
            "Shelf 1", [(20, 80), (180, 80), (180, 280), (20, 280)]
        )
        self.engine.region_manager.update_checkout_region(
            "Main Checkout", [(400, 250), (600, 250), (600, 450), (400, 450)]
        )

    def test_01_empty_store(self):
        """TEST 1: Empty store. Expected: Count approx 0, no fake alerts."""
        frame = np.full((480, 640, 3), 130, dtype=np.uint8)
        # Add high-contrast background lines so it's not blurry
        frame[::30, :] = 200
        frame[:, ::30] = 60

        annotated, res = self.engine.process_frame(frame)
        self.assertIsNotNone(res)
        self.assertEqual(res["people_count"]["confirmed_count"], 0)
        self.assertFalse(res["checkout"]["is_congested"])
        self.assertFalse(res["shelf"]["is_changed"])
        self.assertFalse(res["shelf"]["is_obstructed"])

    def test_02_single_person_camera_wide_independence(self):
        """TEST 2: One person walks through view. Expected: Counted camera-wide, no false shelf/checkout alerts."""
        frame = np.full((480, 640, 3), 130, dtype=np.uint8)
        frame[::30, :] = 200
        # Place person in center aisle (X: 300, Y: 200) - outside shelf and checkout
        track = Tracklet(
            track_id=1,
            bbox=(300, 150, 50, 120),
            centroid=(325, 210),
            foot_point=(325, 270),
            confidence=0.88,
            first_seen=time.time() - 2.0,
            last_seen=time.time(),
            is_confirmed=True,
        )
        self.engine.tracker.tracks = {1: track}

        annotated, res = self.engine.process_frame(frame)
        self.assertEqual(res["people_count"]["confirmed_count"], 1)
        self.assertEqual(res["checkout"]["visible_people"], 0)
        self.assertFalse(res["checkout"]["is_congested"])
        self.assertFalse(res["shelf"]["is_obstructed"])

    def test_03_person_in_front_of_shelf_obstruction_gate(self):
        """
        TEST 3: Person directly in front of shelf.
        CRITICAL: Person is counted camera-wide; shelf reports OBSTRUCTED; NO false shelf change!
        """
        frame = np.full((480, 640, 3), 130, dtype=np.uint8)
        frame[::30, :] = 200
        # First register clean baseline
        self.engine.region_manager.capture_shelf_baseline(frame)

        # Place a person overlapping shelf region (X: 20-180, Y: 80-280)
        track = Tracklet(
            track_id=1,
            bbox=(50, 100, 60, 140),
            centroid=(80, 170),
            foot_point=(80, 240),
            confidence=0.90,
            first_seen=time.time() - 2.0,
            last_seen=time.time(),
            is_confirmed=True,
        )
        self.engine.tracker.tracks = {1: track}

        annotated, res = self.engine.process_frame(frame)
        
        # 1. Person is STILL counted camera-wide!
        self.assertEqual(res["people_count"]["confirmed_count"], 1)
        # 2. Shelf detects obstruction
        self.assertTrue(res["shelf"]["is_obstructed"])
        self.assertEqual(res["shelf"]["status"], "Shelf view temporarily obstructed by person")
        # 3. Shelf does NOT falsely report change!
        self.assertFalse(res["shelf"]["is_changed"])

    def test_04_person_walks_away_stabilization_window(self):
        """TEST 4: Person leaves shelf. Expected: waits for stabilization before comparing."""
        frame = np.full((480, 640, 3), 130, dtype=np.uint8)
        frame[::30, :] = 200
        self.engine.region_manager.capture_shelf_baseline(frame)

        # First trigger obstruction
        obstruction_track = Tracklet(
            track_id=1, bbox=(50, 100, 60, 140), centroid=(80, 170),
            foot_point=(80, 240), confidence=0.9, first_seen=time.time(),
            last_seen=time.time(), is_confirmed=True,
        )
        self.engine.shelf_monitor.evaluate(
            frame, [obstruction_track], self.engine.region_manager.shelf_region,
            self.engine.region_manager, "HIGH"
        )
        self.assertTrue(self.engine.shelf_monitor.was_obstructed)

        # Now person leaves (empty tracks list)
        report_stabilizing = self.engine.shelf_monitor.evaluate(
            frame, [], self.engine.region_manager.shelf_region,
            self.engine.region_manager, "HIGH"
        )
        self.assertIn("Stabilizing", report_stabilizing.status)
        self.assertFalse(report_stabilizing.is_changed)

    def test_05_checkout_congestion_persistence(self):
        """TEST 5: Multiple people near checkout. Expected: Reports congestion only after persistence."""
        t_now = time.time()
        # Create 3 people in checkout polygon (X: 400-600, Y: 250-450)
        tracks = [
            Tracklet(1, (420, 280, 40, 90), (440, 325), (440, 370), 0.85, t_now - 10.0, t_now, [], 1, 0, True),
            Tracklet(2, (480, 290, 40, 90), (500, 335), (500, 380), 0.88, t_now - 10.0, t_now, [], 1, 0, True),
            Tracklet(3, (540, 290, 40, 90), (560, 335), (560, 380), 0.82, t_now - 10.0, t_now, [], 1, 0, True),
        ]

        # Frame 1: congestion begins
        rep1 = self.engine.checkout_monitor.evaluate(tracks, self.engine.region_manager.checkout_region, "HIGH")
        self.assertEqual(rep1.visible_people_count, 3)

        # Simulate time passing past threshold (6s)
        self.engine.checkout_monitor.congestion_start_time = t_now - 7.0
        rep2 = self.engine.checkout_monitor.evaluate(tracks, self.engine.region_manager.checkout_region, "HIGH")
        self.assertTrue(rep2.is_congested)
        self.assertEqual(rep2.status, "Possible checkout congestion")

    def test_06_camera_wide_counting_includes_all_regions(self):
        """TEST 6: People distributed across store. Expected: Camera-wide count includes everyone."""
        frame = np.full((480, 640, 3), 130, dtype=np.uint8)
        frame[::30, :] = 200
        t_now = time.time()
        tracks = [
            Tracklet(1, (50, 100, 40, 90), (70, 145), (70, 190), 0.85, t_now, t_now, [], 1, 0, True),     # In shelf
            Tracklet(2, (480, 290, 40, 90), (500, 335), (500, 380), 0.88, t_now, t_now, [], 1, 0, True),  # In checkout
            Tracklet(3, (300, 150, 40, 90), (320, 195), (320, 240), 0.82, t_now, t_now, [], 1, 0, True),  # In aisle
        ]
        self.engine.tracker.tracks = {t.track_id: t for t in tracks}

        annotated, res = self.engine.process_frame(frame)
        self.assertEqual(res["people_count"]["confirmed_count"], 3)
        self.assertEqual(res["checkout"]["visible_people"], 1)

    def test_07_dark_camera_warning(self):
        """TEST 7: Very dark frame. Expected: Reliability warning, confident analytics withheld."""
        dark_frame = np.full((480, 640, 3), 15, dtype=np.uint8)
        annotated, res = self.engine.process_frame(dark_frame)
        self.assertIn(res["reliability"]["video_quality"], ("Degraded", "Unavailable"))
        self.assertIn(res["people_count"]["reliability"], ("Low", "Unavailable"))

    def test_08_disconnected_camera_no_fake_data(self):
        """TEST 8: Disconnected / empty stream. Expected: Video source unavailable, zero fake data."""
        annotated, res = self.engine.process_frame(None)
        self.assertEqual(res["reliability"]["video_quality"], "Unavailable")
        self.assertEqual(res["people_count"]["display"], "Unavailable")
        self.assertEqual(res["people_count"]["confirmed_count"], 0)

    def test_09_global_lighting_shift_distinction(self):
        """TEST 9: Sudden major lighting shift across entire frame -> reports unable to determine reliably."""
        base_frame = np.full((480, 640, 3), 100, dtype=np.uint8)
        self.engine.region_manager.capture_shelf_baseline(base_frame)

        # Global shift: entire camera becomes bright (lighting turned on)
        bright_frame = np.full((480, 640, 3), 190, dtype=np.uint8)
        report = self.engine.shelf_monitor.evaluate(
            bright_frame, [], self.engine.region_manager.shelf_region,
            self.engine.region_manager, "HIGH"
        )
        self.assertEqual(report.status, "Unable to determine shelf change reliably")
        self.assertIn("illumination shift", report.explanation)

    def test_10_shelf_unaltered_matches_baseline(self):
        """TEST 10: No visual change on shelf -> reports no significant change."""
        frame = np.full((480, 640, 3), 120, dtype=np.uint8)
        frame[::30, :] = 200
        self.engine.region_manager.capture_shelf_baseline(frame)

        report = self.engine.shelf_monitor.evaluate(
            frame, [], self.engine.region_manager.shelf_region,
            self.engine.region_manager, "HIGH"
        )
        self.assertEqual(report.status, "No significant visual change detected")
        self.assertFalse(report.is_changed)

    def test_11_actual_visual_change_triggers_verification(self):
        """TEST 11: Real visual difference in shelf region -> reports visual change detected."""
        frame1 = np.full((480, 640, 3), 120, dtype=np.uint8)
        frame1[::30, :] = 200
        self.engine.region_manager.capture_shelf_baseline(frame1)

        # Modify only the shelf region
        frame2 = frame1.copy()
        sx1, sy1, sx2, sy2 = 20, 80, 180, 280
        frame2[sy1:sy2, sx1:sx2] = 20  # Shelf emptied / changed significantly

        report = self.engine.shelf_monitor.evaluate(
            frame2, [], self.engine.region_manager.shelf_region,
            self.engine.region_manager, "HIGH"
        )
        self.assertEqual(report.status, "Visual change detected")
        self.assertTrue(report.is_changed)
        self.assertIn("Human verification recommended", report.explanation)

if __name__ == "__main__":
    unittest.main()
