class Property:
    def __init__(self, area, rooms, price, address):
        self.area = area
        self.rooms = rooms
        self.price = price
        self.address = address


class House(Property):
    def __init__(self, area, rooms, price, address, plot):
        super().__init__(area, rooms, price, address)
        self.plot = plot

    def __str__(self):
        return (
            f"House at {self.address}: {self.area} m2, {self.rooms} rooms, "
            f"plot {self.plot} m2, price {self.price} PLN"
        )


class Flat(Property):
    def __init__(self, area, rooms, price, address, floor):
        super().__init__(area, rooms, price, address)
        self.floor = floor

    def __str__(self):
        return (
            f"Flat at {self.address}: {self.area} m2, {self.rooms} rooms, "
            f"floor {self.floor}, price {self.price} PLN"
        )


if __name__ == "__main__":
    house = House(150, 5, 1_200_000, "Forest Street 4, Krakow", 800)
    flat = Flat(55, 3, 650_000, "River Street 10/12, Warsaw", 4)
    print(house)
    print(flat)
