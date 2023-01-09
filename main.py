import functions_framework
from logging import DEBUG


# Register an HTTP function with the Functions Framework
@functions_framework.http
def my_http_function(request):
    # Your code here

    # Return an HTTP response
    return "OK"


if __name__ == "main":
    from flask import Flask

    app = Flask(__name__)
    app.logger.setLevel(DEBUG)

    @app.route("/payload", methods=["POST"])
    def payload(request):
        app.logger.debug("Request received:")
        app.logger.debug(request)
        return {}

    @app.errorhandler(404)
    def not_found(error):
        app.logger.debug(error)
        response = {
            "code"       : error.code,
            "description": error.description,
            "name"       : error.name
        }
        return response
