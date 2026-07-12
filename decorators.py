import csv
from functools import wraps
import inspect
import datetime


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
        print(f"Called {func.__name__} with {args},{kwargs}")
        try:
            return_value = func(*args, **kwargs)
        except Exception as e:
            print(f"{func.__name__} raised an exception: {e}")
            raise
        else:
            print(f"{func.__name__} returned {return_value}")
            return return_value

    return wrapper


def logging(log_file_path : str):
    class Decorator:
        log_file = None

        def __init__(self, log_path : str):
            need_header = False
            try:
                with open(log_path, "r"):
                    pass
            except FileNotFoundError:
                need_header = True
            try:
                Decorator.log_file = open(log_path, "a", newline="")
            except OSError:
                print(f"Couldn't open log file: {log_path}")
                raise
            self.log_writer = csv.writer(Decorator.log_file)
            if need_header:
                self.log_writer.writerow(["DateTime","Function Name", "Args"])
                Decorator.log_file.flush()

        def __call__(self, func):
            def wrapper(*args, **kwargs):
                row = [datetime.datetime.now(), func.__name__, *args]
                self.log_writer.writerow(row)
                Decorator.log_file.flush()
                return func(*args, **kwargs)
            return wrapper
    return Decorator(log_file_path)

