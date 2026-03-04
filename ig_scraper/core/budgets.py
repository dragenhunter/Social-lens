class Budget:
    def __init__(self, limits):
        self.limits = limits or {}
        self.used = {k: 0 for k in self.limits}

    def consume(self, key):
        limit = self.limits.get(key)
        if limit is None or limit <= 0:
            return

        used = self.used.get(key, 0)
        if used >= limit:
            raise RuntimeError(f"Budget exceeded: {key}")
        self.used[key] = used + 1
