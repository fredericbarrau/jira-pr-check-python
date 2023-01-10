# Jira Github PR Check

Cloud function used as a Github Webhook.
Will check if a PR name is properly linked to a jira ticket.

The current document is for the cloud function hosted in Google Cloud that will be called from Github in order to validate the branch names in project.

A proper branch name must follow the jira convention, and contain an issue name.

## Usage

Locally:

```console
$ functions_framework --target=jira_github_pr_check
Runs on port localhost:8080
```

In Cloud Run, using gcloud for deployment (test only):

```console
$ gcloud deploy github-jira-webhook --source . --runtime python310 --entry-point jira_github_pr_check
...
```

## Configuration

The cloud function grabs the configuration secrets from environment variables.
These environment variables contain secrets, and should be provided to the cloud function during deployment (see the dedicated terraform code).

For local development, a `dev/.env` file can be created (ignored by git) in order to add these configurations and secrets, see below.

## Development

**VSCode:** for convenience, development / debugging of this cloud function should be done in a dedicated vscode workspace containing the current source folder **only**. The root folder of the cloud function sources contains a vscode configuration file (`.vscode/launch.json`) which, when in a dedicated workspace, provides the configuration for using the debugger of the [python](https://marketplace.visualstudio.com/items?itemName=ms-python.python) extension.


### Dependency management

This project uses [poetry](https://python-poetry.org/) for managing the the project dependencies.

Generate the `requirements.txt` for the google cloud builder with the following command once a new dependency has been added / removed:

```console
$ poetry export --without-hashes --format=requirements.txt > requirements.txt
```

### Local development

#### Configure the dev/.env file

```ini
# dev/.env file
JIRA_DOMAIN=altirnao.atlassian.net
# See https://docs.python.org/3/library/logging.html#logging-levels
LOG_LEVEL=10
JIRA_EMAIL=frederic.barrau@altirnao.com
# See gcloud secret:
# List the versions:
# gcloud secrets versions list jira-github-pr-check-user-token
# Get the value for the latest version X:
# gcloud secrets versions access X --secret jira-github-pr-check-user-token
JIRA_TOKEN=< see google cloud secrets> 
```

#### Running the cloud function locally

```console
$ poetry shell
Spawning shell within /Users/fredericbarrau/Library/Caches/pypoetry/virtualenvs/jira-github-pr-check-python-I_CHN4P6-py3.10
$ poetry install
Installing dependencies from lock file

No dependencies to install or update
$ functions_framework --target=jira_github_pr_check
...
```


#### Exposing the cloud function with ngrok

Ngrok in a tool for providing a public access of a local development service. 

```console

```

### Local debugging

As mentionned above, the current folder contains a `.vscode/launch.json` file which, when used in a dedicated workspace, provides the configuration for the debugger of the [python](https://marketplace.visualstudio.com/items?itemName=ms-python.python) vscode extension.


## Notes

### Refs

* `ref/heads/main`

