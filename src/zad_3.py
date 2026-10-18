def is_even(number: int) -> bool:
    return number % 2 == 0


if __name__ == "__main__":
    result = is_even(7)
    if result:
        print("Liczba parzysta")
    else:
        print("Liczba nieparzysta")
