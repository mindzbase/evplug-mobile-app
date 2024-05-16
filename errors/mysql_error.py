import logging
import json
from aiohttp import web

LOGGER = logging.getLogger("server")


class MySQLError(Exception):
    message: str

    def __init__(self, message) -> None:
        super().__init__(f"Error occured during MYSQL opration : {message}")


class MissingInfoException(Exception):
    def __init__(self, message):
        self.message = message


class InvalidInfoException(Exception):
    def __init__(self, variable_name):
        self.message = f"Variable '{variable_name}' is invalid"

    def __str__(self):
        return f"InvalidInfoException: {self.message}"


class PaymentMethodInvalid(Exception):
    def __init__(self, code=1000):
        self.code = code
        self.message = f"Something Went Wrong with Status Code : {code}"

    def __str__(self):
        return self.message


class PaymentIntentInvalid(Exception):
    def __init__(self, code=1001):
        self.code = code
        self.message = f"Something Went Wrong with Status Code : {code}"

    def __str__(self):
        return self.message


class ParameterMissing(Exception):
    def __init__(
        self,
        title="Request not completed.",
        msg="Necessary parameters missing.",
        status=400,
    ):
        self.title = title
        self.msg = msg
        self.jsonResponse = web.Response(
            status=status,
            body=json.dumps({"title": self.title, "msg": self.msg}),
            content_type="application/json",
        )
        super().__init__(self.msg)


class ValidateInstance(Exception):
    def __init__(self, **kwargs):
        self.msg = f"parameter {kwargs['variable']} is type of {kwargs['type']}"
        super().__init__(self.msg)


def check_empty_info(*args, **kwargs):
    if args:
        kwargs.update(args[0])
    try:
        for var_name, var_value in kwargs.items():
            if not var_value and var_value != 0:
                raise InvalidInfoException(var_name)
    except InvalidInfoException as e:
        LOGGER.error(e)


# try:
#     check_empty_info(a=a, c=b)
#     check_empty_info({"a":a, "c":b})
# except MissingInfoException as e:
#     print(e)


class MissingObjectOnDB(Exception):
    def __init__(self, object, status=400):
        self.title = "Request not completed."
        self.msg = f"{object} record is not found."
        self.jsonResponse = web.Response(
            status=status,
            body=json.dumps({"title": self.title, "msg": self.msg}),
            content_type="application/json",
        )
        super().__init__(self.msg)
