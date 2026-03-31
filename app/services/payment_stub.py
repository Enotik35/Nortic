def get_test_payment_links(order_id: int) -> dict:
    return {
        "card": f"https://example.com/pay/card?order_id={order_id}",
        "crypto": f"https://example.com/pay/crypto?order_id={order_id}",
        "stars": f"https://example.com/pay/stars?order_id={order_id}",
    }