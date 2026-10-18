def double_with_for(numbers):
    result = []
    for number in numbers:
        result.append(number * 2)
    return result


def double_with_comprehension(numbers):
    return [number * 2 for number in numbers]


if __name__ == "__main__":
    numbers = [1, 2, 3, 4, 5]
    print(double_with_for(numbers))
    print(double_with_comprehension(numbers))
