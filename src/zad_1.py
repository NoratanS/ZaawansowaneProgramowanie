from library.student import Student

if __name__ == "__main__":
    good_student = Student("Anna", [70, 85, 60])
    weak_student = Student("Tom", [30, 45, 50])
    print(good_student.name, good_student.is_passed())
    print(weak_student.name, weak_student.is_passed())
