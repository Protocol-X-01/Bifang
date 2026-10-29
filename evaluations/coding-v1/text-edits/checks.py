import unittest

from module import apply_edits


class Checks(unittest.TestCase):
    def test_original_offsets_and_input_order(self):
        edits = [(4, 6, "!"), (0, 1, "LONG")]
        self.assertEqual(apply_edits("abcdef", edits), "LONGbcd!")
        self.assertEqual(edits, [(4, 6, "!"), (0, 1, "LONG")])

    def test_unicode_insert_delete_and_touching(self):
        self.assertEqual(apply_edits("a🙂bc", [(1, 2, "X"), (2, 3, "")]), "aXc")
        self.assertEqual(apply_edits("ab", [(0, 0, "<"), (2, 2, ">")]), "<ab>")
        self.assertEqual(apply_edits("abc", []), "abc")

    def test_invalid_ranges(self):
        for edits in ([(-1, 1, "")], [(0, 4, "")], [(2, 1, "")],
                      [(0, 2, ""), (1, 3, "")], [(1, 1, "a"), (1, 2, "b")]):
            with self.subTest(edits=edits), self.assertRaises(ValueError):
                apply_edits("abc", edits)
        for edits in ([(True, 2, "")], [(0.0, 1, "")], [(0, 1, None)]):
            with self.subTest(edits=edits), self.assertRaises((TypeError, ValueError)):
                apply_edits("abc", edits)


if __name__ == "__main__":
    unittest.main()
