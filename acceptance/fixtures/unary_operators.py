# Expected total mutation sites: 4
# Unary operators: not (1 site), unary - (1 site); in and is not are Compare sites
def check(a, b, x, y):
    if not x:  # site 1: not (unary, new)
        return -y  # site 2: - (unary, new)
    return (a in b, a is not b)  # sites 3-4: in, is not (existing Compare sites)
