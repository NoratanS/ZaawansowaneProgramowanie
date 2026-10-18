import pytest

from utils import (
    calculate_discount,
    count_vowels,
    fibonacci,
    flatten_list,
    is_palindrome,
    is_prime,
    word_frequencies,
)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("kajak", True),
        ("Kobyła ma mały bok", True),
        ("python", False),
        ("", True),
        ("A", True),
    ],
)
def test_is_palindrome(text, expected):
    assert is_palindrome(text) == expected


@pytest.mark.parametrize("n, expected", [(0, 0), (1, 1), (5, 5), (10, 55)])
def test_fibonacci(n, expected):
    assert fibonacci(n) == expected


def test_fibonacci_negative_raises():
    with pytest.raises(ValueError):
        fibonacci(-1)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Python", 2),
        ("AEIOUY", 6),
        ("bcd", 0),
        ("", 0),
        # Spec says 4, but with Polish vowels (ą, ę, ó) it is ó, a, ó, i, a = 5.
        ("Próba żółwia", 5),
    ],
)
def test_count_vowels(text, expected):
    assert count_vowels(text) == expected


@pytest.mark.parametrize(
    "price, discount, expected",
    [(100, 0.2, 80.0), (50, 0, 50.0), (200, 1, 0.0)],
)
def test_calculate_discount(price, discount, expected):
    assert calculate_discount(price, discount) == pytest.approx(expected)


@pytest.mark.parametrize("discount", [-0.1, 1.5])
def test_calculate_discount_out_of_range_raises(discount):
    with pytest.raises(ValueError):
        calculate_discount(100, discount)


@pytest.mark.parametrize(
    "nested_list, expected",
    [
        ([1, 2, 3], [1, 2, 3]),
        ([1, [2, 3], [4, [5]]], [1, 2, 3, 4, 5]),
        ([], []),
        ([[[1]]], [1]),
        ([1, [2, [3, [4]]]], [1, 2, 3, 4]),
    ],
)
def test_flatten_list(nested_list, expected):
    assert flatten_list(nested_list) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("To be or not to be", {"to": 2, "be": 2, "or": 1, "not": 1}),
        ("Hello, hello!", {"hello": 2}),
        ("", {}),
        ("Python Python python", {"python": 3}),
        (
            "Ala ma kota, a kot ma Ale.",
            {"ala": 1, "ma": 2, "kota": 1, "a": 1, "kot": 1, "ale": 1},
        ),
    ],
)
def test_word_frequencies(text, expected):
    assert word_frequencies(text) == expected


@pytest.mark.parametrize(
    "n, expected",
    [
        (2, True),
        (3, True),
        (4, False),
        (0, False),
        (1, False),
        (5, True),
        (97, True),
    ],
)
def test_is_prime(n, expected):
    assert is_prime(n) == expected
