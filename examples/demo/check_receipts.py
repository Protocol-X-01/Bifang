import unittest

from receipts import parse_receipt


class ReceiptChecks(unittest.TestCase):
    def test_plain_fields(self):
        self.assertEqual(parse_receipt("Cafe,Food,4.50"), {
            "merchant": "Cafe", "category": "Food", "amount": "4.50",
        })

    def test_quoted_comma(self):
        self.assertEqual(parse_receipt('"Cafe, North",Food,4.50')["merchant"], "Cafe, North")

    def test_escaped_quote(self):
        self.assertEqual(parse_receipt('"The ""Daily"" Cafe",Food,4.50')["merchant"], 'The "Daily" Cafe')

    def test_trailing_newline(self):
        self.assertEqual(parse_receipt("Cafe,Food,4.50\n")["amount"], "4.50")

    def test_wrong_field_count(self):
        with self.assertRaises(ValueError):
            parse_receipt("Cafe,Food")


if __name__ == "__main__":
    unittest.main()
