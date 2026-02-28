class Governor:
    def __init__(self):
        self.mult = 1.0

    def degrade(self):
        self.mult = min(self.mult * 1.5, 4.0)

    def recover(self):
        self.mult = max(1.0, self.mult * 0.9)
