import unittest
from bounds import valid
class BoundaryTests(unittest.TestCase):
    def test_boundaries(self):
        self.assertFalse(valid(1, [0]))
        self.assertFalse(valid(-1, [0]))
        self.assertTrue(valid(0, [0]))
        self.assertFalse(valid(0, []))
