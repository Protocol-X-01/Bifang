import unittest

from module import dependency_order


class Checks(unittest.TestCase):
    def test_order_is_not_name_sort(self):
        self.assertEqual(dependency_order({"deploy": ["test"], "test": ["build"],
                                           "build": []}), ["build", "test", "deploy"])

    def test_reconsider_ready_jobs_after_each_step(self):
        self.assertEqual(dependency_order({"z": [], "b": ["a"], "a": []}),
                         ["a", "b", "z"])

    def test_cycles_and_unknown(self):
        for graph in ({"a": ["a"]}, {"a": ["b"], "b": ["a"]}, {"a": ["missing"]}):
            with self.subTest(graph=graph), self.assertRaises(ValueError):
                dependency_order(graph)

    def test_empty_duplicates_and_input_preservation(self):
        self.assertEqual(dependency_order({}), [])
        graph = {"a": ["b", "b"], "b": []}
        self.assertEqual(dependency_order(graph), ["b", "a"])
        self.assertEqual(graph, {"a": ["b", "b"], "b": []})


if __name__ == "__main__":
    unittest.main()
