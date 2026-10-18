def wyswietl_parzyste(liczby):
    for liczba in liczby:
        if liczba % 2 == 0:
            print(liczba)


if __name__ == "__main__":
    wyswietl_parzyste(list(range(1, 11)))
