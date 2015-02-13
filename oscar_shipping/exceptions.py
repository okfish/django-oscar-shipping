class FacadeError(Exception):
    """Base class for shipping facades exceptions """
    pass

class ApiOfflineError(FacadeError):
    """Raised when API is offline

    Attributes:
        title -- title to find
        
    """
    pass

# WARNING! Inheriting exception classes may cause strange behavior
# while raising it. 
class CityNotFoundError(FacadeError):
    """Raised when an attempt to find city code by title failed 

    Attributes:
        title -- title to find
        errors -- extra info
    """
    def __init__(self, title, errors=None):
        self.title = title
        self.errors = errors
        
class OriginCityNotFoundError(CityNotFoundError):
    """Raised when an attempt to find ORIGIN city code by title failed 

    Attributes:
        title -- title to find
        errors -- extra info
    """
    pass

class TooManyFoundError(FacadeError):
    """Raised when an attempt to find city code return more than one code 

    Attributes:
        title -- title to find
        errors -- extra info contains full API answer
    """
    def __init__(self, title, errors):
        self.title = title
        self.errors = errors