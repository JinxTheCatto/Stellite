import unittest

import numpy as np

import charts


def keys(chart, hold=0.05):
    actions = sorted(charts.note_actions(chart, hold), key=lambda action: (action[0], action[1]))
    return [(round(time, 3), kind) for time, order, kind, lane in actions]


def draw_notes(positions, lane=2):
    # a strip of chart picture the way CHOpt draws it: filled circles with a black rim, each drawn over the one before
    image = np.full((120, 400, 3), 255, np.uint8)
    y = 20 + charts.LANE_GAP * lane
    rim = charts.CIRCLE.astype(bool)
    inside = np.zeros_like(rim)
    for row in range(rim.shape[0]):
        columns = np.flatnonzero(rim[row])
        inside[row, columns[0]:columns[-1] + 1] = True
    for x in positions:
        patch = image[y - 5:y + 6, x - 5:x + 6]
        patch[inside] = (0, 165, 255)
        patch[rim] = (0, 0, 0)
    return image, [(20, 0.0, 6.0)]


class LiftNoteTests(unittest.TestCase):
    # placed notes are (seconds, lane, has a sustain, overdrive note)
    def lifts(self, placed):
        return sorted(charts.find_lifts(placed))

    def test_single_note_repeated_very_quickly_is_hit_by_letting_go(self):
        # seen in recordings: pairs 67, 78, 88 and 94 ms apart are one tall note
        for gap in (0.067, 0.078, 0.088, 0.094):
            self.assertEqual(self.lifts([(10.0, 2, False, False), (10.0 + gap, 2, False, False)]), [1], gap)

    def test_16ths_at_normal_speed_are_two_presses(self):
        # 16ths at 156 and 150 bpm: letting go on the second one missed it every time
        for gap in (0.0962, 0.1, 0.117, 0.128):
            self.assertEqual(self.lifts([(10.0, 2, False, False), (10.0 + gap, 2, False, False)]), [], gap)

    def test_a_run_pairs_up_two_by_two(self):
        self.assertEqual(self.lifts([(10.0 + 0.067 * index, 4, False, False) for index in range(4)]), [1, 3])
        self.assertEqual(self.lifts([(10.0 + 0.067 * index, 4, False, False) for index in range(5)]), [1, 3])

    def test_overdrive_notes_pair_up_too(self):
        self.assertEqual(self.lifts([(10.0 + 0.067 * index, 0, False, True) for index in range(4)]), [1, 3])

    def test_chords_and_sustains_stay_presses(self):
        self.assertEqual(self.lifts([(10.0, 0, False, False), (10.0, 3, False, False), (10.08, 0, False, False), (10.08, 3, False, False)]), [])  # chords
        self.assertEqual(self.lifts([(10.0, 0, False, False), (10.08, 0, True, False)]), [])  # the second one is a sustain
        self.assertEqual(self.lifts([(10.0, 0, True, False), (10.08, 0, False, False)]), [])  # the first one is a sustain

    def test_a_note_after_a_chord_is_pressed_and_can_start_a_pair(self):
        placed = [(10.0, 1, False, False), (10.0, 3, False, False), (10.08, 1, False, False), (10.16, 1, False, False)]
        self.assertEqual(self.lifts(placed), [3])

    def test_keys_press_once_and_let_go_on_the_lift(self):
        chart = {
            "notes": [(10.0, 2, 0.0), (10.08, 2, 0.0), (10.16, 2, 0.0), (10.24, 2, 0.0), (11.0, 2, 0.0)],
            "lift_notes": [(10.08, 2), (10.24, 2)],
        }
        self.assertEqual(keys(chart), [(10.0, "hold"), (10.08, "lift"), (10.16, "hold"), (10.24, "lift"), (11.0, "press"), (11.05, "release")])

    def test_lift_notes_are_found_by_time_when_the_notes_were_learned_from_the_screen(self):
        # a screen-learned chart has slightly different note times than the source chart the lifts come from
        chart = {"notes": [(10.01, 2, 0.0), (10.09, 2, 0.0)], "lift_notes": [(10.08, 2)]}
        self.assertEqual(keys(chart), [(10.01, "hold"), (10.09, "lift")])

    def test_charts_without_lifts_play_as_before(self):
        chart = {"notes": [(1.0, 0, 0.0), (1.03, 0, 0.0), (2.0, 0, 0.5), (2.4, 0, 0.0)]}
        self.assertEqual(keys(chart), [(1.0, "press"), (1.02, "release"), (1.03, "press"), (1.08, "release"), (2.0, "hold"), (2.39, "release"), (2.4, "press"), (2.45, "release")])


class TouchingNotesTests(unittest.TestCase):
    def found(self, positions):
        image, rows = draw_notes(positions)
        return [x for beat, lane, row, x, overdrive in charts.find_notes(image, rows) if lane == 2]

    def test_notes_apart_are_all_found(self):
        self.assertEqual(self.found([100, 130, 160]), [100, 130, 160])

    def test_every_note_of_a_run_that_touches_is_found(self):
        # twelve notes a sixth of a beat apart: the spacing goes 10, 9, 11 pixels, and the middle one of each three has
        # its right side covered by the next. It used to be skipped, 8 of the 12 were read
        positions = [100, 110, 119, 130, 140, 149, 160, 170, 179, 190, 200, 209]
        self.assertEqual(self.found(positions), positions)

    def test_a_pair_that_touches_is_two_notes(self):
        self.assertEqual(self.found([100, 109]), [100, 109])
        self.assertEqual(self.found([100, 108, 200]), [100, 108, 200])


if __name__ == "__main__":
    unittest.main()
