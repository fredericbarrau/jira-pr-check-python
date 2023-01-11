from dotenv import load_dotenv
from functions_framework import logging
import functions_framework
from jira import JIRA
import os
import regex


log = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%m/%d/%Y %I:%M:%S %p",
)


class NotJiraIssueException(Exception):
    """
    Raised when a Github branch is not referenced as a Jira issue
    """

    pass


def get_jira_issue_from_branch_name(branch_name: str) -> str:
    match = regex.findall(
        r"(?<= |^)([0-9A-Z][A-Za-z]{1,10}-[0-9]+)(?= |$)", branch_name
    )
    # Search for the first issue found in the commit message
    return match[1] if match is not None else match


def is_jira_issue(config: dict, issue_id: str) -> bool:
    result = True
    try:
        jira = JIRA(
            server="https://" + config["jira_domain"],
            basic_auth=(config["jira_email"], config["jira_token"]),
        )
        log.debug(f"looking of issue '{issue_id}' in Jira..")
        # will trigger an exception when the issue is not found
        jira.issue(issue_id)
        log.debug(f"{issue_id} found in Jira")
    except Exception as e:
        log.debug(e)
        result = False
    return result


def get_branch_name_from_ref(git_ref: str) -> str | None:
    branch_name_re = "^refs/heads/(.*)$"
    match = regex.match(branch_name_re, git_ref)
    return match[1] if match is not None else match


def get_config() -> dict:
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
    return config


# Register an HTTP function with the Functions Framework
@functions_framework.http
def jira_github_pr_check(request):
    code = 200
    result = "OK"
    config = get_config()
    # Set the log level
    log.setLevel(config["log_level"])
    log.info(f"log level: {log.level}")
    try:
        payload = request.get_json()
        branch_name = payload["pull_request"]["head"]["ref"]
        if branch_name is None:
            log.debug("branch name not found in the github payload")
            raise ValueError(
                "Github payload is not a proper JSON: github webhook must send a JSON payload in application/json MIME type. Review the webhook settings"
            )
        log.debug(f"branch name found: {branch_name}")
        issue_id = get_jira_issue_from_branch_name(branch_name)
        log.debug(f"issue id found ({issue_id}) in branch name {branch_name}")
        if issue_id is None:
            log.error(
                f"branch name {branch_name} does not fit the JIRA branch name requirements"
            )
            raise NotJiraIssueException(
                f"branch name {branch_name} does not fit the JIRA branch name requirements"
            )
        if not is_jira_issue(config=config, issue_id=issue_id):
            log.debug(f"issue ID {issue_id} is not a jira issue")
            raise NotJiraIssueException(
                f"branch name {branch_name} does not reference a JIRA issue. Issue Id ({issue_id}) not found in JIRA."
            )
        log.info(
            f"branch name ({branch_name}) references a found Jira issue ({issue_id})"
        )
    except NotJiraIssueException as e:
        log.error(e)
        result = {"message": str(e)}
        code = 404
    except Exception as e:
        log.error(e)
        result = {"message": str(e)}
        code = 400
    return result, code
