def print_every_second(numbers):
    for number in numbers[::2]:
        print(number)


if __name__ == "__main__":
    print_every_second(list(range(1, 11)))
