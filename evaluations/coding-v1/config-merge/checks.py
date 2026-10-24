import unittest

from module import merge_config


class Checks(unittest.TestCase):
    def test_nested_overlay(self):
        self.assertEqual(merge_config({"db": {"host": "local", "port": 5432}},
                                     {"db": {"port": 5433}}),
                         {"db": {"host": "local", "port": 5433}})

    def test_replacement_and_none(self):
        self.assertEqual(merge_config({"items": [1, 2], "flag": True},
                                     {"items": [], "flag": None}),
                         {"items": [], "flag": None})

    def test_no_aliases(self):
        base = {"base_only": [1], "nested": {"keep": [2]}}
        overlay = {"nested": {"new": [3]}}
        result = merge_config(base, overlay)
        result["base_only"].append(4)
        result["nested"]["new"].append(5)
        self.assertEqual(base, {"base_only": [1], "nested": {"keep": [2]}})
        self.assertEqual(overlay, {"nested": {"new": [3]}})

    def test_empty_and_type_change(self):
        self.assertEqual(merge_config({}, {}), {})
        self.assertEqual(merge_config({"item": 1}, {"item": {"new": 2}}),
                         {"item": {"new": 2}})


if __name__ == "__main__":
    unittest.main()
