from dotenv import load_dotenv
from functions_framework import logging
from github import Github
from jira import JIRA
import functions_framework
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


def get_jira_issue_from_branch_name(branch_name: str) -> str:
    match = regex.findall(
        r"(?<= |-|_|^)([0-9A-Z][A-Za-z]{1,10}-[0-9]+)(?= |-|_|$)",
        branch_name,
    )
    # Search for the first issue found in the commit message
    return match[0] if len(match) > 0 else None


def is_jira_issue(config: dict, issue_id: str) -> bool:
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
    config["github_token"] = os.getenv("GITHUB_TOKEN")
    return config


def push_github_commit_status(commit_status: dict) -> bool:
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


# Register an HTTP function with the Functions Framework
@functions_framework.http
def jira_github_pr_check(request):
    code = 200
    result = "OK"

    config = get_config()

    # Initalize commit status
    github_commit_status = {
        "commit_sha": None,
        "repository_name": None,
        "github_token": config["github_token"],
        "message": "failed to check if branch name has a jira issue (probably not)",
        "callback_url": request.url,
        "status": "failure",
    }

    # Set the log level
    log.setLevel(config["log_level"])

    try:
        payload = request.get_json()
        branch_name = payload["pull_request"]["head"]["ref"]
        if branch_name is None:
            log.debug("branch name not found in the github payload")
            raise ValueError(
                "Github payload is not a proper JSON: github webhook must send a JSON payload in application/json MIME type. Review the webhook settings"
            )
        log.debug("branch name found: %s", branch_name)

        # amend github commit status
        github_commit_status["commit_sha"] = payload["pull_request"]["head"]["sha"]
        github_commit_status["repository_name"] = payload["pull_request"]["head"][
            "repo"
        ]["full_name"]

        issue_id = get_jira_issue_from_branch_name(branch_name)
        if issue_id is None:
            raise NotJiraIssueException(
                f"branch name {branch_name} does not fit the JIRA branch name requirements"
            )
        log.debug("issue id found (%s) in branch name %s", issue_id, branch_name)
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

    except NotJiraIssueException as e:
        error_message = str(e)
        github_commit_status["message"] = error_message

        log.error(e)
        result = {"message": error_message}
        code = 404
    except Exception as e:
        error_message = str(e)
        github_commit_status["message"] = error_message

        log.error(e)
        result = {"message": error_message}
        code = 400

    try:
        # Send github commit status
        push_github_commit_status(github_commit_status)
    except Exception as e:
        log.error(e)
        result = {"message": str(e)}
        code = 500

    return result, code
