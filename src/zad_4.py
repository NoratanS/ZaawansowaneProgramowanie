def wyswietl_co_drugi(liczby):
    for liczba in liczby[::2]:
        print(liczba)


if __name__ == "__main__":
    wyswietl_co_drugi(list(range(1, 11)))
