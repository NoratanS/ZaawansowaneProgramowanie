def merge_unique_cubed(first: list[int], second: list[int]) -> list[int]:
    unique = dict.fromkeys(first + second)  # removes duplicates, keeps order
    return [x**3 for x in unique]


if __name__ == "__main__":
    print(merge_unique_cubed([1, 2, 3], [2, 3, 4]))
