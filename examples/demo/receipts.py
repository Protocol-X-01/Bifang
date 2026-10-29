def parse_receipt(row: str) -> dict[str, str]:
    merchant, category, amount = row.strip().split(",")
    return {"merchant": merchant, "category": category, "amount": amount}
