import magazine.utils


class Product:
    def __init__(self, name: str, price: float):
        self.name = name
        self.price = price

    def __str__(self):
        return f"{self.name}: {magazine.utils.format_price(self.price)}"


if __name__ == "__main__":
    print(Product("Pen", 2.5))
