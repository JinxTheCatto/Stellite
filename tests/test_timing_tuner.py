import unittest

import numpy as np

from timing_tuner import TimingTuner, VisualGradeReader, classify_grade


class TimingTunerTests(unittest.TestCase):
    def test_all_perfect_baseline_keeps_offset_without_trials(self):
        tuner = TimingTuner(-20, batch_size=2)

        tuner.observe("perfect")
        update = tuner.observe("perfect")

        self.assertEqual(update["phase"], "complete")
        self.assertFalse(update["save"])
        self.assertEqual(update["offset_ms"], -20)
        self.assertTrue(tuner.finished)

    def test_goods_trigger_bounded_trials_and_select_best_batch(self):
        tuner = TimingTuner(-20, batch_size=2, step_ms=5)

        tuner.observe("good")
        earlier = tuner.observe("perfect")
        self.assertEqual(earlier["offset_ms"], -25)
        self.assertEqual(earlier["phase"], "trial")

        tuner.observe("good")
        later = tuner.observe("good")
        self.assertEqual(later["offset_ms"], -15)

        tuner.observe("perfect")
        selected = tuner.observe("perfect")
        self.assertEqual(selected["offset_ms"], -15)
        self.assertTrue(selected["save"])
        self.assertTrue(tuner.finished)

    def test_tied_results_keep_baseline_and_incomplete_trial_restores_it(self):
        tuner = TimingTuner(10, batch_size=1)
        tuner.observe("good")
        tuner.observe("good")
        selected = tuner.observe("good")
        self.assertEqual(selected["offset_ms"], 10)
        self.assertFalse(selected["save"])

        incomplete = TimingTuner(10, batch_size=2)
        incomplete.observe("good")
        incomplete.observe("good")
        incomplete.observe("perfect")
        self.assertEqual(incomplete.finish(), 10)


class GradeRecognitionTests(unittest.TestCase):
    def test_classifies_clear_and_slightly_noisy_grade_text(self):
        self.assertEqual(classify_grade("PERFECTO", 0.9), "perfect")
        self.assertEqual(classify_grade("PERFECTOT", 0.9), "perfect")
        self.assertEqual(classify_grade("BUENO", 0.9), "good")
        self.assertIsNone(classify_grade("PERFECTO", 0.4))
        self.assertIsNone(classify_grade("MISS", 0.99))

    def test_reads_only_new_single_combo_increments(self):
        class FakeOCR:
            def __init__(self):
                self.results = iter((
                    ([["10", 0.99]], []),
                    ([["11", 0.99]], []),
                    ([["PERFECTO", 0.95]], []),
                    ([["13", 0.99]], []),
                    ([["14", 0.99]], []),
                    ([["GOOD", 0.95]], []),
                ))

            def __call__(self, _image, **_kwargs):
                return next(self.results)

        reader = VisualGradeReader.__new__(VisualGradeReader)
        reader.ocr = FakeOCR()
        reader.last_combo = None
        frame = np.ones((20, 20), dtype=np.uint8)
        region = (0, 0, 10, 10)

        self.assertIsNone(reader.observe(frame, region, region))
        self.assertEqual(reader.observe(frame, region, region), "perfect")
        self.assertIsNone(reader.observe(frame, region, region))
        self.assertEqual(reader.observe(frame, region, region), "good")


if __name__ == "__main__":
    unittest.main()
