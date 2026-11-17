import json
import os
import tempfile
import unittest
from unittest.mock import patch

import charts


class LearnedChartTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.directory.name, "learned_charts.json")
        self.song = {"name": "Test Song", "shortname": "test_song"}
        self.notes = [(0.0, 0, 0.0), (0.5, 2, 1.25)]
        self.file_patch = patch.object(charts, "LEARNED_CHARTS_FILE", self.path)
        self.file_patch.start()
        self.addCleanup(self.file_patch.stop)
        self.addCleanup(self.directory.cleanup)

    def test_saves_and_loads_screen_chart(self):
        self.assertTrue(charts.save_learned_chart(self.song, "drums", self.notes))

        learned = charts.load_learned_chart(self.song, "drums")

        self.assertTrue(learned["learned"])
        self.assertEqual(learned["notes"], self.notes)
        self.assertEqual(learned["length"], None)

    def test_does_not_replace_a_more_complete_chart(self):
        charts.save_learned_chart(self.song, "drums", self.notes)

        saved = charts.save_learned_chart(self.song, "drums", self.notes[:1])

        self.assertFalse(saved)
        self.assertEqual(len(charts.load_learned_chart(self.song, "drums")["notes"]), 2)

    def test_replaces_larger_learned_chart_when_source_validation_fails(self):
        source = {
            "instrument": "drums",
            "notes": [(0.0, 0, 0.0), (1.0, 4, 0.9)],
        }
        invalid_notes = [(0.0, 0, 0.0)] + [(index, 4, 0.0) for index in range(5)]
        valid_notes = [(0.0, 0, 0.0), (1.0, 4, 0.9)]
        charts.save_learned_chart(self.song, "drums", invalid_notes)

        saved = charts.save_learned_chart(self.song, "drums", valid_notes, source)

        self.assertTrue(saved)
        self.assertEqual(charts.load_learned_chart(self.song, "drums")["notes"], valid_notes)

    def test_ignores_malformed_learned_data(self):
        with open(self.path, "w", encoding="utf-8") as file:
            json.dump({"test_song:drums": {"notes": [[0, 1.5, 0]]}}, file)

        self.assertIsNone(charts.load_learned_chart(self.song, "drums"))

    def test_missing_store_is_not_an_error(self):
        self.assertIsNone(charts.load_learned_chart(self.song, "drums"))

    def test_quality_accepts_matching_lane_counts_and_sustains(self):
        source = {
            "notes": [(0.0, 0, 0.0), (0.5, 0, 0.0), (1.0, 4, 0.9)],
        }
        learned = {
            "notes": [(0.0, 0, 0.0), (0.51, 0, 0.0), (1.02, 4, 1.0)],
        }

        self.assertIsNone(charts.learned_chart_quality(learned, source))

    def test_quality_rejects_excess_lane_notes_and_sustains(self):
        source = {
            "notes": [(0.0, 0, 0.0), (1.0, 4, 0.9)],
        }
        learned = {
            "notes": [(0.0, 0, 0.0)] + [(index, 4, 6.0) for index in range(5)],
        }

        issue = charts.learned_chart_quality(learned, source)

        self.assertIsNotNone(issue)

    def test_quality_rejects_a_lane_missing_too_many_notes(self):
        source = {"notes": [(index, 2, 0.0) for index in range(10)]}
        learned = {"notes": [(index, 2, 0.0) for index in range(8)]}

        issue = charts.learned_chart_quality(learned, source)

        self.assertEqual(issue, "lane 3 has 8 learned notes versus 10 in the source chart")

    def test_quality_rejects_missing_drum_sustain(self):
        source = {
            "instrument": "drums",
            "notes": [(0.0, 0, 0.0), (1.0, 4, 0.9)],
        }
        learned = {
            "notes": [(0.0, 0, 0.0), (1.0, 4, 0.0)],
        }

        self.assertIsNotNone(charts.learned_chart_quality(learned, source))

    def test_restores_drum_sustain_from_source_chart_by_lane_position(self):
        source = {
            "instrument": "drums",
            "notes": [(0.0, 4, 0.0), (0.5, 4, 0.0), (1.0, 4, 0.9)],
        }
        learned = {
            "notes": [(0.0, 4, 0.0), (0.55, 4, 0.0), (0.95, 4, 0.0)],
        }

        restored = charts.restore_source_drums_sustains(learned["notes"], source)

        self.assertEqual(restored[-1], (0.95, 4, 0.9))
        self.assertIsNone(charts.learned_chart_quality({"notes": restored}, source))

if __name__ == "__main__":
    unittest.main()
