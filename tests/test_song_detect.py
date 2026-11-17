import unittest

import song_detect

SONGS = [
    {"name": "A Bar Song by Shaboozey"},
    {"name": "Everlong by Foo Fighters"},
    {"name": "Godzilla by Blue Öyster Cult"},
    {"name": "Bohemian Rhapsody by Queen"},
]


class SongDetectTests(unittest.TestCase):
    def test_parts_in_spanish_and_english(self):
        self.assertEqual(song_detect.parse_part("ENTO PRINCIPAL"), ("lead", False))
        self.assertEqual(song_detect.parse_part("BATERÍA"), ("drums", False))
        self.assertEqual(song_detect.parse_part("Vocals"), ("vocals", False))
        self.assertEqual(song_detect.parse_part("voz"), ("vocals", False))
        self.assertEqual(song_detect.parse_part("BAJO PRO"), ("bass", True))
        self.assertEqual(song_detect.parse_part("PRO LEAD"), ("lead", True))
        self.assertEqual(song_detect.parse_part(""), (None, False))

    def test_long_part_name_cut_off_by_its_box(self):
        # "INSTRUMENTO PRINCIPAL" scrolls inside a box that is too small for it
        for piece in ("INSTRUMENTO PR", "NSTRUMENTO PRI", "TRUMENTO PRINCIP", "ENTO PRINCIPAL", "O PRINCIPAL"):
            self.assertEqual(song_detect.parse_part(piece), ("lead", False), piece)
        self.assertEqual(song_detect.parse_part("BAJO"), ("bass", False))

    def test_expert_and_header(self):
        self.assertTrue(song_detect.is_expert("EXTREMO"))
        self.assertTrue(song_detect.is_expert("Expert"))
        self.assertFalse(song_detect.is_expert("DIFÍCIL"))
        self.assertTrue(song_detect.is_ready_screen("¡PREPÁRATE!"))
        self.assertTrue(song_detect.is_ready_screen("GET READY!"))
        self.assertFalse(song_detect.is_ready_screen("1:23"))

    def test_matches_title_and_artist_with_ocr_noise(self):
        self.assertEqual(song_detect.match_song(SONGS, "A Bar Song", "Shaboozey")["name"], "A Bar Song by Shaboozey")
        self.assertEqual(song_detect.match_song(SONGS, "Everlonq", "Foo Fiqhters")["name"], "Everlong by Foo Fighters")
        self.assertEqual(song_detect.match_song(SONGS, "Bohemian Rhaps...", "Queen")["name"], "Bohemian Rhapsody by Queen")

    def test_rejects_songs_that_are_not_in_the_list(self):
        self.assertIsNone(song_detect.match_song(SONGS, "Godzilla", "Eminem"))
        self.assertIsNone(song_detect.match_song(SONGS, "", ""))


if __name__ == "__main__":
    unittest.main()
