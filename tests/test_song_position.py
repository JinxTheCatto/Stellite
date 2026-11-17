import unittest

import numpy as np

import charts
import song_detect


def riff_chart(repeats=40, period=2.0):
    # the same eight notes again and again, the way most songs go
    riff = [(0.0, 0), (0.25, 3), (0.5, 2), (0.75, 0), (1.0, 0), (1.25, 3), (1.5, 2), (1.75, 4)]
    notes = [(10.0 + index * period + offset, lane, 0.0) for index in range(repeats) for offset, lane in riff]
    return {"end": 10.0 + repeats * period + 5, "notes": notes}


def mixed_chart(seconds=120, seed=3):
    # ten notes a second on keys that follow no pattern, so a run of them fits one spot only
    rng = np.random.default_rng(seed)
    return {"end": seconds + 5.0, "notes": [(5.0 + index * 0.1, int(rng.integers(0, 5)), 0.0) for index in range(seconds * 10)]}


def play(sync, chart, offset, start, count, timer=False, error=0.0, lead=0.05):
    # The notes from `start` seconds into the song come by on screen, with the song's true clock at `offset`.
    # `lead` is how long the chart was switched on before the first of them. timer adds what the game's song timer
    # says once a second, off by `error`. Returns when the clock locked
    notes = sorted(note for note in chart["notes"] if note[0] >= start)[:count]
    sync.resume(offset + notes[0][0] - lead)
    next_read = offset + notes[0][0] - 1.5
    for when, lane, length in notes:
        now = offset + when
        while timer and next_read <= now:
            sync.hint_position(next_read, next_read - offset + error)
            next_read += 1.0
        sync.add_sighting(now, lane)
        if sync.try_lock(now):
            return now
    return None


class GameTimerTests(unittest.TestCase):
    def test_a_riff_that_repeats_cannot_be_placed_by_its_notes_alone(self):
        # the chart was switched on a moment after the notes began: every repeat of the riff fits them just as well
        chart = riff_chart()
        sync = charts.ChartSync(chart)
        self.assertIsNone(play(sync, chart, 1000.0, 30.0, 60))

    def test_the_game_timer_says_which_repeat_it_is(self):
        chart = riff_chart()
        for error in (-0.7, 0.0, 0.7):
            sync = charts.ChartSync(chart)
            locked = play(sync, chart, 1000.0, 30.0, 60, timer=True, error=error)
            self.assertIsNotNone(locked, error)
            self.assertLess(locked - 1030.0, 2.0) # within the first notes, not after the riff changed
            self.assertAlmostEqual(sync.model[0], 1000.0, delta=0.03)
            self.assertEqual(sync.locked_by, "timer")

    def test_the_start_of_a_song_still_locks_on_four_notes(self):
        chart = riff_chart()
        sync = charts.ChartSync(chart)
        locked = play(sync, chart, 1000.0, 10.0, 60, timer=True, error=0.3, lead=3.0)
        self.assertAlmostEqual(locked, 1010.75, delta=0.01)
        self.assertAlmostEqual(sync.model[0], 1000.0, delta=0.03)

    def test_one_chord_again_and_again_is_placed_by_the_quiet_before_it(self):
        # the same chord every 0.35 s: one chord further on fits the same notes, and the timer is not that sharp.
        # The chart was already on before the first chord came, so the first one seen is the first one there is
        chart = {"end": 60.0, "notes": [(22.5 + 0.35 * index, lane, 0.0) for index in range(12) for lane in (1, 4)]}
        sync = charts.ChartSync(chart)
        locked = play(sync, chart, 1000.0, 22.0, 24, timer=True, error=0.4, lead=3.0)
        self.assertIsNotNone(locked)
        self.assertAlmostEqual(sync.model[0], 1000.0, delta=0.03)

    def test_a_wrong_song_length_gives_way_to_notes_that_fit_one_spot(self):
        # the timer points six seconds off. Nothing fits there, so after a while the notes decide, and from then on
        # the timer is read with that difference taken off
        chart = mixed_chart()
        sync = charts.ChartSync(chart)
        locked = play(sync, chart, 1000.0, 40.0, 120, timer=True, error=6.0)
        self.assertIsNotNone(locked)
        self.assertAlmostEqual(sync.model[0], 1000.0, delta=0.03)
        self.assertEqual(sync.locked_by, "notes")
        self.assertAlmostEqual(sync.hinted_position(locked), locked - 1000.0, delta=1.0)

    def test_a_reading_from_long_ago_is_not_used(self):
        chart = riff_chart()
        sync = charts.ChartSync(chart)
        sync.hint_position(1000.0, 0.0)
        self.assertIsNone(sync.hinted_position(1000.0 + charts.ChartSync.HINT_AGE + 1))
        self.assertAlmostEqual(sync.hinted_position(1002.0), 2.0)

    def test_timer_text_as_the_screen_reader_gets_it(self):
        self.assertEqual(song_detect.parse_time_left("-2:41"), 161)
        self.assertEqual(song_detect.parse_time_left("-0:07"), 7)
        # the slanted font: the colon goes missing, a 1 comes out as a t
        self.assertEqual(song_detect.parse_time_left("-228"), 148)
        self.assertEqual(song_detect.parse_time_left("-t:51"), 111)
        self.assertEqual(song_detect.parse_time_left(" -t13 "), 73)
        # a lost minute or anything that is not a time is no reading at all
        self.assertIsNone(song_detect.parse_time_left("-:18"))
        self.assertIsNone(song_detect.parse_time_left("-11"))
        self.assertIsNone(song_detect.parse_time_left("-1:75"))
        self.assertIsNone(song_detect.parse_time_left("Epic Games"))
        self.assertIsNone(song_detect.parse_time_left(""))


class ClockJumpTests(unittest.TestCase):
    def locked(self, chart):
        sync = charts.ChartSync(chart)
        sync.start_at(1000.0, 0.0)
        sync.manual = False
        sync.aligned = 0.0
        return sync

    def see(self, sync, chart, start, end, late, every=1):
        # notes of that stretch show up on screen `late` seconds after the chart clock (as it was at the start) has them
        for index, (when, lane, length) in enumerate(note for note in chart["notes"] if start <= note[0] < end):
            if index % every == 0:
                sync.add_sighting(1000.0 + when + late, lane)

    def test_a_few_notes_one_note_late_do_not_move_a_clock_that_plays_fine(self):
        # a hit effect read as a note shows up a tenth of a second after the note it belongs to. Six of those among
        # twenty notes that were played fine used to move the clock by a whole note, and teach it a wrong speed
        chart = mixed_chart()
        sync = self.locked(chart)
        self.see(sync, chart, 30.0, 32.0, 0.1, every=3)
        self.assertEqual(sync.realigns, 0)
        self.assertAlmostEqual(sync.wall_time(40.0), 1040.0, delta=0.005)

    def test_a_clock_that_really_is_late_still_jumps(self):
        # every note of the last seconds going by a tenth late is what a clock that is off looks like
        chart = mixed_chart()
        sync = self.locked(chart)
        self.see(sync, chart, 30.0, 32.0, 0.1)
        self.assertEqual(sync.realigns, 1)
        self.assertAlmostEqual(sync.wall_time(32.0), 1032.1, delta=0.02)

    def test_a_jump_straight_back_takes_the_learned_speed_with_it(self):
        chart = mixed_chart()
        sync = self.locked(chart)
        self.see(sync, chart, 30.0, 32.0, 0.1)
        self.assertGreater(sync.drift_ms(), 1.0) # a tenth late after 30 s reads as a clock that runs slow
        self.see(sync, chart, 32.0, 34.0, 0.0)
        self.assertEqual(sync.realigns, 2)
        self.assertAlmostEqual(sync.drift_ms(), 0.0, delta=0.01)
        self.assertAlmostEqual(sync.wall_time(60.0), 1060.0, delta=0.02)


if __name__ == "__main__":
    unittest.main()
