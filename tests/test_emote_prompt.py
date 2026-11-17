import unittest

import numpy as np

from emote_prompt import EmotePromptReader, is_gesto_prompt


def ocr_result(*items):
    return [([0, 0, 0, 0], text, confidence) for text, confidence in items]


class EmotePromptTests(unittest.TestCase):
    def test_requires_clear_b_and_gesto_labels(self):
        self.assertTrue(is_gesto_prompt(ocr_result(("B", 0.96), ("GESTO", 0.99))))
        self.assertTrue(is_gesto_prompt(ocr_result(("B GESTO", 0.99))))
        self.assertFalse(is_gesto_prompt(ocr_result(("B", 0.96), ("GESTO", 0.5))))
        self.assertFalse(is_gesto_prompt(ocr_result(("GESTO", 0.99))))
        self.assertFalse(is_gesto_prompt(ocr_result(("B", 0.99), ("MENU", 0.99))))

    def test_taps_once_per_prompt_and_rearms_after_prompt_disappears(self):
        class FakeOCR:
            def __init__(self):
                self.results = iter((
                    ocr_result(("B", 0.96), ("GESTO", 0.99)),
                    ocr_result(("B", 0.96), ("GESTO", 0.99)),
                    [],
                    [],
                    ocr_result(("B", 0.96), ("GESTO", 0.99)),
                ))

            def __call__(self, _image):
                return next(self.results), None

        reader = EmotePromptReader(FakeOCR())
        frame = np.ones((20, 20), dtype=np.uint8)
        region = (0, 0, 10, 10)

        self.assertTrue(reader.observe(frame, region, 0.0))
        self.assertFalse(reader.observe(frame, region, 0.1))
        self.assertFalse(reader.observe(frame, region, 0.2))
        self.assertFalse(reader.observe(frame, region, 0.8))
        self.assertTrue(reader.observe(frame, region, 0.9))

    def test_rejects_empty_prompt_region(self):
        reader = EmotePromptReader(lambda _image: ([], None))

        with self.assertRaisesRegex(ValueError, "outside the captured frame"):
            reader.observe(np.zeros((10, 10)), (0, 0, 20, 20), 0.0)


if __name__ == "__main__":
    unittest.main()
