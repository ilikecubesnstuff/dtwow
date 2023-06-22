def clumped(iterable, n):
    it = iter(iterable)
    while True:
        clump = []
        for _ in range(n):
            try:
                clump.append(next(it))
            except StopIteration:
                if clump:
                    yield clump
                return
        yield clump