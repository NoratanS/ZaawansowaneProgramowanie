def contains(values: list[int], value: int) -> bool:
    return value in values


if __name__ == "__main__":
    print(contains([1, 2, 3], 2))
    print(contains([1, 2, 3], 5))
