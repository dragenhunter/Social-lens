class Budget:
    def __init__(self, limits):
        self.limits = limits
        self.used = {k: 0 for k in limits}

    def consume(self, key):
        if self.used[key] >= self.limits[key]:
            raise RuntimeError(f"Budget exceeded: {key}")
        self.used[key] += 1
