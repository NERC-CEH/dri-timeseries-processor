"""A simple module entrypoint for running the code. Runs for 10 minutes and then exits."""

from time import sleep

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
