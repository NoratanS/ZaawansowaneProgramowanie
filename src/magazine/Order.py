import magazine.utils


class Order:
    def __init__(self, products: list):
        self.products = products

    def total(self) -> float:
        return sum(product.price for product in self.products)

    def __str__(self):
        lines = [str(product) for product in self.products]
        lines.append(f"Total: {magazine.utils.format_price(self.total())}")
        return "\n".join(lines)


if __name__ == "__main__":
    print(Order([]))
