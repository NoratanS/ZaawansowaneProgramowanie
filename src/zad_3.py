def print_even(numbers):
    for number in numbers:
        if number % 2 == 0:
            print(number)


if __name__ == "__main__":
    print_even(list(range(1, 11)))
