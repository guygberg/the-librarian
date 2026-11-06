"""The error every Person action raises to refuse a request: an HTTP-style status and a message."""


class Invalid(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message
