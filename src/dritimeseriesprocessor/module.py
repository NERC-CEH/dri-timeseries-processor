"""This module contains a single method, demonstrating the structure"""

from time import sleep


def add_int(x: int, y: int) -> int:
    """Adds two integers together

    Args:
        x: The first number
        y: The second number

    Returns:
        int: The result
    """

    return x + y


if __name__ == "__main__":
    print("START")

    index = 0

    while True:
        print(f"index = {index}.")
        sleep(5)
        index += 1

        # Break after 10 minutes
        if index >= 120:
            break

    print("END")
