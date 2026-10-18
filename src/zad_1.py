class Student:
    def __init__(self, name, marks):
        self.name = name
        self.marks = marks

    def is_passed(self):
        return sum(self.marks) / len(self.marks) > 50

    def __str__(self):
        return f"Student: {self.name}, marks: {self.marks}"


if __name__ == "__main__":
    good_student = Student("Anna", [70, 85, 60])
    weak_student = Student("Tom", [30, 45, 50])
    print(good_student.name, good_student.is_passed())
    print(weak_student.name, weak_student.is_passed())
