import unittest

import numpy as np

from screen_learning import ScreenChartLearner


class ScreenChartLearnerTests(unittest.TestCase):
    def setUp(self):
        self.learner = ScreenChartLearner(5, 20, 50)
        self.learner.reset(recording=True, song={"name": "Test"}, instrument="lead")

    @staticmethod
    def detection(center_x, center_y, hold=False, height=10, pressable=True):
        return (
            center_x - 5,
            center_y - height // 2,
            10,
            height,
            0.9,
            hold,
            center_y,
            pressable,
        )

    def test_emits_one_note_when_detections_cross_the_press_line(self):
        image = np.zeros((100, 100), dtype=np.uint8)
        times = [1.0, 1.02, 1.04, 1.06, 1.08]
        centers = [35, 42, 48, 52, 60]
        events = []
        for now, center in zip(times, centers):
            events.extend(self.learner.process_frame(image, [self.detection(10, center)], now))

        self.assertEqual(len(events), 1)
        self.assertEqual(self.learner.notes[0][1], 0)

    def test_merges_overlapping_tile_and_hold_detections(self):
        image = np.zeros((100, 100), dtype=np.uint8)
        self.learner.process_frame(image, [self.detection(10, 42)], 0.9)
        detections = [
            self.detection(10, 52),
            self.detection(10, 60, hold=True, height=80, pressable=False),
        ]

        events = self.learner.process_frame(image, detections, 1.0)

        self.assertEqual(len(events), 1)
        self.assertEqual(len(self.learner.notes), 1)
        self.assertIn(0, self.learner.holds)

    def test_suppresses_duplicate_lane_detections_in_adjacent_frames(self):
        image = np.zeros((100, 100), dtype=np.uint8)
        self.learner.process_frame(image, [self.detection(10, 42)], 0.9)
        first = self.learner.process_frame(image, [self.detection(10, 52)], 1.0)
        self.learner.process_frame(image, [self.detection(10, 62)], 1.01)
        self.learner.process_frame(image, [self.detection(10, 80)], 1.02)
        duplicate = self.learner.process_frame(image, [self.detection(10, 88)], 1.03)

        self.assertEqual(len(first), 1)
        self.assertEqual(duplicate, [])
        self.assertEqual(len(self.learner.notes), 1)

    def test_preserves_normal_confidence_pressability(self):
        image = np.zeros((100, 100), dtype=np.uint8)
        self.learner.process_frame(image, [self.detection(10, 42, pressable=False)], 0.9)
        event = self.learner.process_frame(
            image,
            [self.detection(10, 52, pressable=False)],
            1.0,
        )

        self.assertEqual(event, [(0, 10, 52, False)])

    def test_records_sustain_until_tail_disappears(self):
        image = np.zeros((100, 100), dtype=np.uint8)
        self.learner.process_frame(image, [self.detection(10, 42)], 0.9)
        event = self.learner.process_frame(
            image,
            [self.detection(10, 52, hold=True)],
            1.0,
        )
        self.assertEqual(len(event), 1)

        image[49:52, 7:14] = 220
        self.learner.process_frame(image, [], 1.1)
        for now in (1.2, 1.22, 1.24):
            image[49:52, 7:14] = 0
            self.learner.process_frame(image, [], now)

        self.assertGreater(self.learner.notes[0][2], 0.2)
        self.assertLess(self.learner.notes[0][2], 0.3)

    def test_drum_notes_are_not_misclassified_as_sustains(self):
        image = np.full((100, 100), 220, dtype=np.uint8)
        self.learner.reset(recording=True, song={"name": "Test"}, instrument="drums")
        self.learner.process_frame(image, [self.detection(10, 42)], 0.9)

        self.learner.process_frame(image, [self.detection(10, 52, hold=True)], 1.0)

        self.assertEqual(self.learner.notes[0][2], 0.0)
        self.assertNotIn(0, self.learner.holds)

    def test_stationary_low_confidence_match_is_not_a_note(self):
        image = np.zeros((100, 100), dtype=np.uint8)
        events = []
        for now in (1.0, 1.04, 1.08, 1.12):
            events.extend(self.learner.process_frame(image, [self.detection(10, 52, pressable=False)], now))

        self.assertEqual(events, [])
        self.assertEqual(self.learner.notes, [])


if __name__ == "__main__":
    unittest.main()
