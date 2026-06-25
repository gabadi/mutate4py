# Expected total mutation sites: 6
# Operators: +, -, *, >, ==, and
def compute(a, b):
    x = a + b   # site 1: +
    y = a - b   # site 2: -
    z = a * b   # site 3: *
    if a > b:   # site 4: >
        if a == b:   # site 5: ==
            return a and b  # site 6: and
    return z
