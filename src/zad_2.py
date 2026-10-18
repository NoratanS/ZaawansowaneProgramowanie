from zad_1 import Student


class Library:
    def __init__(self, city, street, zip_code, open_hours, phone):
        self.city = city
        self.street = street
        self.zip_code = zip_code
        self.open_hours = open_hours
        self.phone = phone

    def __str__(self):
        return (
            f"Library: {self.street}, {self.zip_code} {self.city}, "
            f"open {self.open_hours}, phone {self.phone}"
        )


class Employee:
    def __init__(
        self,
        first_name,
        last_name,
        hire_date,
        birth_date,
        city,
        street,
        zip_code,
        phone,
    ):
        self.first_name = first_name
        self.last_name = last_name
        self.hire_date = hire_date
        self.birth_date = birth_date
        self.city = city
        self.street = street
        self.zip_code = zip_code
        self.phone = phone

    def __str__(self):
        return (
            f"Employee: {self.first_name} {self.last_name}, born {self.birth_date}, "
            f"hired {self.hire_date}, "
            f"address: {self.street}, {self.zip_code} {self.city}, "
            f"phone {self.phone}"
        )


class Book:
    def __init__(
        self, library, publication_date, author_name, author_surname, number_of_pages
    ):
        self.library = library
        self.publication_date = publication_date
        self.author_name = author_name
        self.author_surname = author_surname
        self.number_of_pages = number_of_pages

    def __str__(self):
        return (
            f"Book by {self.author_name} {self.author_surname}, "
            f"published {self.publication_date}, "
            f"{self.number_of_pages} pages\n    {self.library}"
        )


class Order:
    def __init__(self, employee, student, books, order_date):
        self.employee = employee
        self.student = student
        self.books = books
        self.order_date = order_date

    def __str__(self):
        books = "\n".join(f"  - {book}" for book in self.books)
        return (
            f"Order from {self.order_date}\n"
            f"  {self.employee}\n"
            f"  {self.student}\n"
            f"  Books:\n{books}"
        )


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
