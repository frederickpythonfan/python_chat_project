import logging as _logging
from functools import wraps
import inspect

_module_logger = _logging.getLogger(__name__)


def class_decorator(decorator):
    def real_decorator(cls):
        for method_name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
            if method_name.startswith("__"):
                continue

            setattr(cls, method_name, decorator(method))

        return cls
    return real_decorator


def debug(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        _module_logger.debug("Called %s with %s,%s", func.__name__, args, kwargs)
        try:
            return_value = func(*args, **kwargs)
        except Exception as e:
            _module_logger.exception("%s raised an exception: %s", func.__name__, e)
            raise
        else:
            _module_logger.debug("%s returned %s", func.__name__, return_value)
            return return_value

    return wrapper


def logging(logger_name: str):
    """Class-method decorator that logs every call via the ``logging`` module.

    ``logger_name`` is passed straight to ``logging.getLogger``, so callers
    can keep using a per-class identifier (e.g. "server_log", "client_log")
    to get a dedicated logger, which is routed through whatever handlers
    logging_config.setup_logging() has configured (console + rotating files).
    """
    logger = _logging.getLogger(logger_name)

    class Decorator:
        def __init__(self):
            self.logger = logger

        def __call__(self, func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                self.logger.debug("Called %s with args=%s kwargs=%s",
                                   func.__name__, args, kwargs)
                try:
                    return_value = func(*args, **kwargs)
                except Exception as e:
                    self.logger.exception("%s raised an exception: %s",
                                           func.__name__, e)
                    raise
                else:
                    self.logger.debug("%s returned %s", func.__name__, return_value)
                    return return_value
            return wrapper
    return Decorator()
