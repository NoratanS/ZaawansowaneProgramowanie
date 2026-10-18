def pomnoz_for(liczby):
    wynik = []
    for liczba in liczby:
        wynik.append(liczba * 2)
    return wynik


def pomnoz_lista_skladana(liczby):
    return [liczba * 2 for liczba in liczby]


if __name__ == "__main__":
    liczby = [1, 2, 3, 4, 5]
    print(pomnoz_for(liczby))
    print(pomnoz_lista_skladana(liczby))
