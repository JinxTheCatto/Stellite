class ScreenChartLearner:
    def __init__(self, lane_count, section_size, press_line):
        self.lane_count = lane_count
        self.section_size = section_size
        self.press_line = press_line
        self.reset()

    def reset(self, recording = False, song = None, instrument = None):
        self.recording = recording
        self.song = song
        self.instrument = instrument
        # Drum lane graphics produced false tail matches; use the source chart for drum holds.
        self.detect_sustains = instrument != "drums"
        self.origin = None
        self.notes = []
        self.tracks = []
        self.holds = {}
        self.last_emitted_lane = [None] * self.lane_count
        self.last_frame_time = 0.0

    @staticmethod
    def _has_tail(image, x, y):
        x0, x1 = max(0, x - 4), min(image.shape[1], x + 5)
        y0, y1 = max(0, y - 48), max(0, y - 9)
        if y1 <= y0 or x1 <= x0:
            return False
        rows = (image[y0:y1, x0:x1].max(axis=1) >= 110)
        run = longest = 0
        for bright in rows:
            run = run + 1 if bright else 0
            longest = max(longest, run)
        return int(rows.sum()) >= 8 and longest >= 5

    @staticmethod
    def _tail_at_probe(image, x, y):
        x0, x1 = max(0, x - 3), min(image.shape[1], x + 4)
        y0, y1 = max(0, y - 1), min(image.shape[0], y + 2)
        return int((image[y0:y1, x0:x1] >= 100).sum()) >= 3

    def _record_note(self, lane, x, y, now, hold_hint):
        if not self.recording:
            return
        if self.origin is None:
            self.origin = now
        if lane in self.holds:
            self._finish_hold(lane, now)
        note_index = len(self.notes)
        self.notes.append([max(0.0, now - self.origin), lane, 0.0])
        if self.detect_sustains and (hold_hint or self._has_tail(self._frame, x, y)):
            self.holds[lane] = {
                "note_index": note_index,
                "start": now,
                "x": x,
                "y": y,
                "seen": False,
                "missing": 0,
            }

    def _finish_hold(self, lane, now, duration = None):
        hold = self.holds.pop(lane)
        if duration is None:
            duration = max(0.0, now - hold["start"])
        self.notes[hold["note_index"]][2] = duration

    def _update_holds(self, image, now):
        for lane, hold in list(self.holds.items()):
            elapsed = now - hold["start"]
            if elapsed < 0.07:
                continue
            present = self._tail_at_probe(image, hold["x"], hold["y"])
            if present:
                hold["seen"] = True
                hold["missing"] = 0
            elif hold["seen"]:
                hold["missing"] += 1
                if hold["missing"] >= 3:
                    self._finish_hold(lane, now)
            elif elapsed >= 0.3:
                self._finish_hold(lane, now, 0.0)

    def process_frame(self, image, detections, now):
        if now <= self.last_frame_time:
            return []
        self.last_frame_time = now
        self._frame = image
        self._update_holds(image, now)

        candidates = []
        for x, y, width, height, confidence, hold_hint, anchor_y, screen_pressable in detections:
            center_x = x + width // 2
            center_y = anchor_y
            if center_y < self.press_line - 32:
                continue
            lane = min(center_x // self.section_size, self.lane_count - 1)
            candidates.append((lane, center_x, center_y, width, height, hold_hint, screen_pressable))
        candidates.sort(key=lambda candidate: (candidate[0], candidate[2]))

        deduplicated = []
        for candidate in candidates:
            lane, center_x, center_y, width, height, hold_hint, screen_pressable = candidate
            duplicate = next((
                previous for previous in reversed(deduplicated)
                if previous[0] == lane and center_y - previous[2] <= 18
                and abs(center_x - previous[1]) <= 18
            ), None)
            if duplicate is None:
                deduplicated.append(candidate)
                continue
            index = deduplicated.index(duplicate)
            old_lane, old_x, old_y, old_width, old_height, old_hold_hint, old_pressable = duplicate
            if height < old_height:
                deduplicated[index] = (
                    lane, center_x, center_y, width, height,
                    old_hold_hint or hold_hint, old_pressable or screen_pressable,
                )
            else:
                deduplicated[index] = (
                    old_lane, old_x, old_y, old_width, old_height,
                    old_hold_hint or hold_hint, old_pressable or screen_pressable,
                )

        matched = set()
        events = []
        for lane, center_x, center_y, width, height, hold_hint, screen_pressable in deduplicated:
            choices = []
            for index, track in enumerate(self.tracks):
                if index in matched or track["lane"] != lane or now - track["time"] > 0.15:
                    continue
                delta = abs(center_y - track["y"])
                if delta <= 22:
                    choices.append((delta, index))

            if choices:
                _, index = min(choices)
                track = self.tracks[index]
                matched.add(index)
                track["progress"] = max(track["progress"], center_y - track["first_y"])
                track["observations"] += 1
                track["y"] = center_y
                track["x"] = center_x
                track["time"] = now
                track["hold_hint"] = track["hold_hint"] or hold_hint
                track["screen_pressable"] = track["screen_pressable"] or screen_pressable
            else:
                track = {
                    "lane": lane,
                    "x": center_x,
                    "y": center_y,
                    "first_y": center_y,
                    "progress": 0,
                    "observations": 1,
                    "time": now,
                    "emitted": False,
                    "hold_hint": hold_hint,
                    "screen_pressable": screen_pressable,
                }
                self.tracks.append(track)
                index = len(self.tracks) - 1
                matched.add(index)

            crossed = (
                center_y >= self.press_line
                and track["progress"] >= 6
                and track["observations"] >= 2
            )
            if crossed and not track["emitted"]:
                track["emitted"] = True
                last_emitted = self.last_emitted_lane[lane]
                if last_emitted is not None and now - last_emitted < 0.03:
                    continue
                self.last_emitted_lane[lane] = now
                event = (lane, center_x, center_y, track["screen_pressable"])
                events.append(event)
                self._record_note(lane, center_x, center_y, now, track["hold_hint"])

        self.tracks = [
            track for track in self.tracks
            if now - track["time"] <= 0.15 and track["y"] <= image.shape[0] + 22
        ]
        return events

    def finish_recording(self, now):
        for lane in list(self.holds):
            self._finish_hold(lane, now)
        if not self.recording:
            return None
        result = (self.song, self.instrument, self.notes)
        self.reset()
        return result
