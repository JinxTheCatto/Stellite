import unittest

import charts


class ChartSyncTests(unittest.TestCase):
    def test_start_at_anchors_song_time_and_records_initial_press_lanes(self):
        chart = {
            "end": 10.0,
            "notes": [(1.25, 0, 0.0), (2.0, 2, 0.0)],
        }
        sync = charts.ChartSync(chart)

        sync.start_at(100.0, 1.25, (0,))

        self.assertTrue(sync.locked)
        self.assertTrue(sync.manual)
        self.assertAlmostEqual(sync.song_time(100.0), 1.25)
        self.assertAlmostEqual(sync.wall_time(1.25), 100.0)
        self.assertEqual(sync.initial_press_lanes, {0})

    def test_missing_screen_sightings_do_not_drop_chart_sync(self):
        chart = {
            "end": 30.0,
            "notes": [(index * 0.1, index % 5, 0.0) for index in range(200)],
        }
        sync = charts.ChartSync(chart)
        sync.start_at(100.0, 0.0)

        message = sync.check(103.0, active=True)

        self.assertIsNone(message)
        self.assertTrue(sync.locked)

    def test_manual_sync_accounts_for_playback_offset_when_matching_notes(self):
        chart = {
            "end": 3.0,
            "notes": [(1.0, 0, 0.0), (1.105, 1, 0.0)],
        }
        sync = charts.ChartSync(chart)
        sync.start_at(100.105, 1.0, (0,))

        warning = sync.add_sighting(100.105, 1, playback_offset=-0.105)

        self.assertIsNone(warning)
        self.assertFalse(sync.manual)
        self.assertEqual(len(sync.matches), 1)

    def test_noisy_sightings_in_dense_runs_do_not_pull_the_clock_away(self):
        # dense same-lane runs with detection jitter used to make the clock run ahead by a quarter second
        import numpy as np
        rng = np.random.default_rng(5)
        notes = []
        for bar in range(60):
            start = bar * 2.0
            notes += [(start + step * 0.195, bar % 5, 0.0) for step in range(6)]  # a dense run in one lane
            notes.append((start + 1.6, (bar + 2) % 5, 0.0))  # and one note on its own
        chart = {"end": 125.0, "notes": notes}
        sync = charts.ChartSync(chart)
        sync.start_at(1000.0, 0.0)
        worst = 0.0
        for time, lane, _ in sorted(notes)[1:]:
            worst = max(worst, abs(1000.0 + time - sync.wall_time(time)))
            sync.add_sighting(1000.0 + time + rng.normal(0, 0.025), lane)
        self.assertLess(worst, 0.04)

    def test_follows_a_chart_that_runs_slightly_slow(self):
        notes = [(index * 0.8, index % 5, 0.0) for index in range(200)]
        chart = {"end": 165.0, "notes": notes}
        sync = charts.ChartSync(chart)
        sync.start_at(1000.0, 0.0)
        for time, lane, _ in notes[1:]:
            sync.add_sighting(1000.0 + time * 1.003, lane)
        # 0.3% over 150 s is 450 ms, the clock has to follow it
        self.assertAlmostEqual(sync.wall_time(150.0), 1000.0 + 150.0 * 1.003, delta=0.02)

    def song(self, seconds=120.0, seed=3):
        # an irregular five lane pattern on a 16th note grid, like a real chart
        import numpy as np
        rng = np.random.default_rng(seed)
        notes, time = [], 2.0
        while time < seconds:
            notes.append((round(time, 4), int(rng.integers(0, 5)), 0.0))
            time += 0.0974 * int(rng.choice([1, 2, 2, 3, 4, 4, 6, 8]))
        return {"end": seconds + 5, "notes": notes}

    def test_notes_going_by_late_pull_the_clock_back(self):
        # the game fell 300 ms behind: every note that shows up is that far from where the clock expects it
        chart = self.song()
        sync = charts.ChartSync(chart)
        sync.start_at(1000.0, 0.0)
        behind = 0.3
        for time, lane, _ in chart["notes"][40:52]:
            sync.add_sighting(1000.0 + time + behind, lane)
        self.assertEqual(sync.realigns, 1)
        self.assertAlmostEqual(sync.wall_time(60.0), 1060.0 + behind, delta=0.015)
        self.assertTrue(sync.locked)

    def test_a_clock_that_is_right_is_left_alone(self):
        chart = self.song()
        sync = charts.ChartSync(chart)
        sync.start_at(1000.0, 0.0)
        for index, (time, lane, _) in enumerate(chart["notes"]):
            sync.add_sighting(1000.0 + time + (0.006 if index % 2 else -0.006), lane)
        self.assertEqual(sync.realigns, 0)
        self.assertAlmostEqual(sync.wall_time(60.0), 1060.0, delta=0.012)

    def test_a_shift_of_exactly_one_beat_is_still_found(self):
        # lane 0 has a note every beat, so being one beat off looks perfect there. only the other lanes give it away
        notes = [(1.0 + 0.39 * index, 0, 0.0) for index in range(200)]
        notes += [(1.13 + 1.17 * index, 2 + index % 3, 0.0) for index in range(60)]
        chart = {"end": 100.0, "notes": sorted(notes)}
        sync = charts.ChartSync(chart)
        sync.start_at(1000.0, 0.0)
        for time, lane, _ in chart["notes"][50:90]:
            sync.add_sighting(1000.0 + time + 0.39, lane)
        self.assertAlmostEqual(sync.wall_time(50.0), 1050.39, delta=0.02)

    def test_nonsense_on_the_highway_means_lost_sync(self):
        import numpy as np
        chart = self.song()
        sync = charts.ChartSync(chart)
        sync.start_at(1000.0, 0.0)
        rng = np.random.default_rng(1)
        now = 1030.0
        for _ in range(16):
            now += float(rng.uniform(0.2, 0.5))
            sync.add_sighting(now, int(rng.integers(0, 5)))
        self.assertEqual(sync.check(now, True), "Lost sync with the highway")
        self.assertFalse(sync.locked)

    def opening(self):
        # a fixed opening, then the irregular pattern
        start = [(2.0, 0, 0.0), (2.2, 3, 0.0), (2.5, 1, 0.0), (2.7, 4, 0.0), (3.1, 2, 0.0), (3.3, 0, 0.0), (3.9, 1, 0.0), (4.3, 3, 0.0)]
        rest = [(time + 4.0, lane, length) for time, lane, length in self.song()["notes"]]
        return {"end": 130.0, "notes": start + rest}

    def test_starts_by_itself_on_the_first_four_notes(self):
        chart = self.opening()
        sync = charts.ChartSync(chart)
        sync.resume(990.0)  # the chart was loaded well before the song began
        locked_on = None
        for index, (time, lane, _) in enumerate(chart["notes"][:8]):
            sync.add_sighting(1000.0 + time, lane)
            if sync.try_lock(1000.0 + time):
                locked_on = index + 1
                break
        self.assertEqual(locked_on, 4)
        self.assertAlmostEqual(sync.wall_time(10.0), 1010.0, delta=0.01)

    def test_one_missed_note_at_the_start_still_starts_by_itself(self):
        chart = self.opening()
        sync = charts.ChartSync(chart)
        sync.resume(990.0)
        locked_on = None
        for index, (time, lane, _) in enumerate(chart["notes"][:8]):
            if index == 1:
                continue  # the detector did not see the second note
            sync.add_sighting(1000.0 + time, lane)
            if sync.try_lock(1000.0 + time):
                locked_on = index + 1
                break
        self.assertEqual(locked_on, 5)
        self.assertAlmostEqual(sync.wall_time(10.0), 1010.0, delta=0.01)

    def test_four_notes_are_not_enough_away_from_the_start(self):
        chart = self.opening()
        notes = chart["notes"]
        # autoplay was switched on in the middle of the song, half a second before these notes
        sync = charts.ChartSync(chart)
        sync.resume(1000.0 + notes[40][0] - 0.5)
        for time, lane, _ in notes[40:44]:
            sync.add_sighting(1000.0 + time, lane)
            self.assertFalse(sync.try_lock(1000.0 + time))
        # and when it was on all along, four notes from the middle do not pass for the opening either
        sync = charts.ChartSync(chart)
        sync.resume(990.0)
        for time, lane, _ in notes[40:44]:
            sync.add_sighting(1000.0 + time, lane)
            self.assertFalse(sync.try_lock(1000.0 + time))

    def test_speed_is_learned_from_one_correction_to_the_next(self):
        # the game keeps falling behind by half a percent; after the second correction the clock runs at the game's speed
        chart = self.song(seconds=150.0)
        sync = charts.ChartSync(chart)
        sync.start_at(1000.0, 0.0)
        notes = chart["notes"]
        for start in (60, 160):
            for time, lane, _ in notes[start:start + 8]:
                sync.add_sighting(1000.0 + time * 1.005, lane)
        self.assertEqual(sync.realigns, 2)
        self.assertGreater(sync.drift_ms(), 3.0)
        later = notes[230][0]
        self.assertAlmostEqual(sync.wall_time(later), 1000.0 + later * 1.005, delta=0.04)

    def test_check_summary_reports_how_far_the_screen_is(self):
        chart = {"end": 10.0, "notes": [(1.0, 0, 0.0), (3.0, 1, 0.0), (5.0, 2, 0.0)]}
        sync = charts.ChartSync(chart)
        sync.fine_tune = False
        sync.start_at(100.0, 1.0)
        sync.add_sighting(102.03, 1)
        sync.add_sighting(104.03, 2)
        error_ms, count = sync.check_summary(101.0)
        self.assertEqual(count, 2)
        self.assertAlmostEqual(error_ms, 30.0, places=3)
        self.assertAlmostEqual(sync.wall_time(3.0), 102.0)  # fine tune off, clock untouched


if __name__ == "__main__":
    unittest.main()
