from library.book import Book
from library.employee import Employee
from library.library import Library
from library.order import Order
from library.student import Student

if __name__ == "__main__":
    central = Library("Krakow", "Main Street 1", "30-001", "8:00-20:00", "123-456-789")
    branch = Library("Warsaw", "Long Street 5", "00-950", "10:00-18:00", "987-654-321")

    books = [
        Book(central, "1997-06-26", "Joanne", "Rowling", 223),
        Book(central, "1954-07-29", "John", "Tolkien", 423),
        Book(branch, "1949-06-08", "George", "Orwell", 328),
        Book(branch, "1965-08-01", "Frank", "Herbert", 412),
        Book(central, "1961-01-01", "Stanislaw", "Lem", 204),
    ]

    employees = [
        Employee(
            "Jan",
            "Kowalski",
            "2015-03-01",
            "1980-05-12",
            "Krakow",
            "Green Street 3",
            "30-002",
            "111-222-333",
        ),
        Employee(
            "Maria",
            "Nowak",
            "2019-09-15",
            "1990-11-23",
            "Warsaw",
            "Short Street 7",
            "00-951",
            "444-555-666",
        ),
        Employee(
            "Piotr",
            "Wisniewski",
            "2021-01-10",
            "1995-02-02",
            "Krakow",
            "Oak Street 12",
            "30-003",
            "777-888-999",
        ),
    ]

    students = [
        Student("Anna", [70, 85, 60]),
        Student("Tom", [30, 45, 50]),
        Student("Kasia", [90, 95, 88]),
    ]

    orders = [
        Order(employees[0], students[0], books[:2], "2026-10-01"),
        Order(employees[1], students[2], books[2:], "2026-10-15"),
    ]

    for order in orders:
        print(order)
        print()
