import translation
import unittest

if __name__ == '__main__':
    unittest.main()

class TestBasicTranslation(unittest.TestCase):
    def setUp(self) -> None:
        tr = translation.BotTranslation("languages")
        self.S = tr.get_string

    def test_absent_language(self):
        tr_alienish = self.S("jj", "START")
        tr_english  = self.S("en", "START")
        self.assertEqual(tr_alienish, tr_english)

    def test_absent_string(self):
        self.assertRaises(KeyError, self.S, "en", "UNBEKNOWNSTTOYOU")
        self.assertRaises(KeyError, self.S, "jj", "UNBEKNOWNSTTOYOU2")