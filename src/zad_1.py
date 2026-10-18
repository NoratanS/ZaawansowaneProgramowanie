def greet(name: str, surname: str) -> str:
    return f"Cześć {name} {surname}!"


if __name__ == "__main__":
    greeting = greet("Jan", "Kowalski")
    print(greeting)
