from dotenv import load_dotenv
from functions_framework import logging
from github import Github
from jira import JIRA
import functions_framework
import hashlib
import hmac
import os
import regex

# Setup logger
log = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%m/%d/%Y %I:%M:%S %p",
)


class NotJiraIssueException(Exception):
    """
    Raised when a Github branch is not referenced as a Jira issue
    """


class WebhookNotAuthorizedException(Exception):
    """
    Raised when a Github branch is not referenced as a Jira issue
    """


def check_payload_secret(request: object, config: dict) -> bool:
    """
    Check the payload send if the configuration contains a webhook secret
    See :
    - https://docs.github.com/en/developers/webhooks-and-events/webhooks/securing-your-webhooks
    """

    result = None

    github_hash = request.headers.get("X-Hub-Signature-256")
    # Fetch the request for the hash
    if github_hash is None:
        result = False

    github_webhook_secret = config["github_webhook_secret"]
    if github_webhook_secret is None:
        # no secret provided: no check needed
        result = True
    else:
        signature = hmac.new(
            key=bytes(github_webhook_secret, "latin-1"),
            digestmod=hashlib.sha256,
            msg=request.get_data(),
        ).hexdigest()
        # Check if the transmitted sha256 matches the hash of the content
        # with the webhook's secret
        result = ("sha256=" + signature) == github_hash
        log.debug("check of the SHA256 of the message: %s", result)
    return result


def get_payload_type(payload: str) -> str | None:
    """
    Return the type of the webhook payload received
    """
    pr_type = None
    if "pull_request" in payload:
        pr_type = "pull_request"
    elif "pusher" in payload:
        pr_type = "push"
    return pr_type


def get_jira_issue_from_branch_name(branch_name: str) -> str:
    """
    Extract the Jira issue from the branch name
    Uses the "official" Jira regexp, adapted for python
    re module does not manage properly lookahead : using regex instead
    """
    match = regex.findall(
        r"(?<= |-|_|^)([0-9A-Z][A-Za-z]{1,10}-[0-9]+)(?= |-|_|$)",
        branch_name,
    )
    # Search for the first issue found in the commit message
    return match[0] if len(match) > 0 else None


def is_jira_issue(config: dict, issue_id: str) -> bool:
    """
    Check if the provided issue_id is a proper Jira issue by
    querying Jira API.
    Beware that the visibility of the issue depends of the rights
    of the token provided in the config dict.
    """
    result = True
    try:
        jira = JIRA(
            server="https://" + config["jira_domain"],
            basic_auth=(config["jira_email"], config["jira_token"]),
        )
        log.debug("looking of issue '%s' in Jira..", issue_id)
        # will trigger an exception when the issue is not found
        jira.issue(issue_id)
        log.debug("%s found in Jira", issue_id)
    except Exception as e:
        log.debug(e)
        result = False
    return result


def get_branch_name_from_ref(git_ref: str) -> str | None:
    """
    Regexp for extracting the branch name from a git ref
    """
    branch_name_re = "^refs/heads/(.*)$"
    match = regex.match(branch_name_re, git_ref)
    return match[1] if match is not None else match


def get_config() -> dict:
    """
    Wrapper to fetch the configuration from env vars
    """
    # Load the local dotenv, if present (for dev env mostly)
    load_dotenv(dotenv_path="dev/.env")
    config = {}
    config["jira_domain"] = os.getenv("JIRA_DOMAIN")
    config["log_level"] = (
        int(os.getenv("LOG_LEVEL"))
        if os.getenv("LOG_LEVEL") is not None
        else logging.INFO
    )
    config["jira_email"] = os.getenv("JIRA_EMAIL")
    config["jira_token"] = os.getenv("JIRA_TOKEN")
    config["github_token"] = os.getenv("GITHUB_TOKEN")
    config["github_webhook_secret"] = os.getenv("GITHUB_WEBHOOK_SECRET")
    config["callback_url"] = os.getenv("CALLBACK_URL")
    return config


def push_github_commit_status(commit_status: dict) -> bool:
    """
    Push a Github commit status using the Github API
    These checks are used by PR when Github is properly configured
    See:
    -  https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/about-status-checks
    """
    g = Github(commit_status["github_token"])
    repo = g.get_repo(commit_status["repository_name"])
    log.debug("get github repo %s", repo)
    commit = repo.get_commit(sha=commit_status["commit_sha"])
    log.debug("get github commit %s", commit)

    commit.create_status(
        state=commit_status["status"],
        target_url=commit_status["callback_url"],
        description=commit_status["message"],
        context="branch-name/jira",
    )
    log.debug(
        "send commit status %s for commit sha %s in project %s",
        commit_status["status"],
        commit_status["commit_sha"],
        commit_status["repository_name"],
    )


# Main HTTP cloud function (wraps by flask)
# Name: jira_github_pr_check
@functions_framework.http
def jira_github_pr_check(request):
    # Initialize the defaults response code & content
    send_http_code = 200
    result = "OK"

    # Get the cloud function configuration
    config = get_config()

    # Initalize commit status
    github_commit_status = {
        "commit_sha": None,
        "repository_name": None,
        "github_token": config["github_token"],
        "message": "failed to check if branch name has a jira issue (probably not)",
        "callback_url": config["callback_url"],
        "status": "failure",
    }

    # Set the log level
    log.setLevel(config["log_level"])

    try:
        # Check if github webhook's secret is OK
        if not check_payload_secret(config=config, request=request):
            raise WebhookNotAuthorizedException("webhook secret do not match")

        # Payload MUST be send as a JSON application/json content
        # => beware of the configuration of the Webhook in Github
        payload = request.get_json()
        payload_type = get_payload_type(payload)
        if payload_type != "pull_request":
            raise ValueError(
                "this callback only manages PR webhook. Fix the webhook settings."
            )
        # Grab the ref from the pull_request data in the payload
        branch_name = payload["pull_request"]["head"]["ref"]
        if branch_name is None:
            log.debug("branch name not found in the github payload")
            raise ValueError(
                "Github payload is not a proper JSON: github webhook must send a JSON payload in application/json MIME type. Review the webhook settings"
            )
        log.debug("branch name found: %s", branch_name)

        # amend github commit status: we have the commit & repo
        github_commit_status["commit_sha"] = payload["pull_request"]["head"]["sha"]
        github_commit_status["repository_name"] = payload["pull_request"]["head"][
            "repo"
        ]["full_name"]

        # Is the branch contains a jira issue id ?
        issue_id = get_jira_issue_from_branch_name(branch_name)
        if issue_id is None:
            raise NotJiraIssueException(
                f"branch name {branch_name} does not fit the JIRA branch name requirements"
            )
        log.debug("issue id found (%s) in branch name %s", issue_id, branch_name)
        # Does the jira issue_id found in the branch a REAL jira issue ?
        # -> asking Jira API
        if not is_jira_issue(config=config, issue_id=issue_id):
            log.debug("issue ID %s is not a jira issue", issue_id)
            raise NotJiraIssueException(
                f"branch name {branch_name} does not reference a JIRA issue. Issue Id ({issue_id}) not found in JIRA."
            )
        log.info(
            "branch name (%s) references a found Jira issue (%s)",
            branch_name,
            issue_id,
        )
        # We dit it, we dit it ! (c) Dora
        github_commit_status[
            "message"
        ] = f"branch name ({branch_name}) references a found Jira issue ({issue_id})"
        github_commit_status["status"] = "success"

    # Error management
    except WebhookNotAuthorizedException as e:
        error_message = str(e)
        github_commit_status["message"] = error_message

        log.error(error_message)
        result = {"message": error_message}
        send_http_code = 403
    except NotJiraIssueException as e:
        # That was not a proper jira issue :(
        error_message = str(e)
        github_commit_status["message"] = error_message

        log.error(error_message)
        result = {"message": error_message}
        send_http_code = 404
    except Exception as e:
        # Something went wrong somewhat
        # incorrect jira message format, or whatever
        error_message = str(e)
        github_commit_status["message"] = error_message

        log.error(error_message)
        result = {"message": error_message}
        send_http_code = 400

    try:
        # Send github commit status if error not 403
        if send_http_code != 403:
            push_github_commit_status(github_commit_status)
    except Exception as e:
        log.error(e)
        result = {"message": str(e)}
        send_http_code = 500

    return result, send_http_code
