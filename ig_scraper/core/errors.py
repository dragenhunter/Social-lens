"""Error classes for the scraper."""

class ScraperError(Exception):
    pass

class RecoverableError(ScraperError):
    pass
