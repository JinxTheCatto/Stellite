import unittest

import cv2
import numpy as np

import charts
import overlay


class CanvasStub:
    def __init__(self):
        self.calls = []

    def __getitem__(self, key):
        return {"width": 242, "height": 286}[key]

    def delete(self, *args):
        self.calls.append(("delete", args, {}))

    def create_rectangle(self, *args, **kwargs):
        self.calls.append(("rectangle", args, kwargs))

    def create_text(self, *args, **kwargs):
        self.calls.append(("text", args, kwargs))

    def create_line(self, *args, **kwargs):
        self.calls.append(("line", args, kwargs))

    def create_oval(self, *args, **kwargs):
        self.calls.append(("oval", args, kwargs))

    def create_polygon(self, *args, **kwargs):
        self.calls.append(("polygon", args, kwargs))

    def coords(self, *args):
        self.calls.append(("coords", args, {}))

    def itemconfigure(self, *args, **kwargs):
        self.calls.append(("itemconfigure", args, kwargs))


class OverdriveOverlayTests(unittest.TestCase):
    def test_find_notes_marks_star_sprites_as_overdrive(self):
        image = np.full((250, 500, 3), 255, dtype=np.uint8)
        star = charts.STAR.astype(bool)
        image[94:106, 95:106][star] = 0

        notes = charts.find_notes(image, [(100, 0.0, 6.0)])

        self.assertEqual(len(notes), 1)
        self.assertTrue(notes[0][4])

    def test_overdrive_markers_are_white_stars(self):
        canvas = CanvasStub()
        overlay.draw_highway(canvas, {
            "lanes": ["d", "f", "j", "k", "l"],
            "notes": [(2, 1.0, "overdrive")],
            "held": [],
            "status": "LIVE",
        })

        stars = [call for call in canvas.calls if call[0] == "polygon"]
        self.assertEqual(len(stars), 1)
        self.assertEqual(stars[0][2]["fill"], "#ffffff")


if __name__ == "__main__":
    unittest.main()
