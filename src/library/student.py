class Student:
    def __init__(self, name, marks):
        self.name = name
        self.marks = marks

    def is_passed(self):
        return sum(self.marks) / len(self.marks) > 50

    def __str__(self):
        return f"Student: {self.name}, marks: {self.marks}"
