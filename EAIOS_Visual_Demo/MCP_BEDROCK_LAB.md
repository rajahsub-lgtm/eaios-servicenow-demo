# EAIOS MCP and Bedrock learning lab

Run commands from EAIOS_Visual_Demo.

## Setup and execution

Install optional lab dependencies:
    .\.venv\Scripts\python.exe -m pip install -r requirements-lab.txt

Use an AWS temporary-credential profile named eaios-learning.
Model: us.amazon.nova-micro-v1:0
AWS client region: us-east-2
Inference consumes applicable credits or incurs usage charges.

Set the simulated role:
    $env:EAIOS_LAB_ROLE = "investigator"

Configure LangSmith tracing in the current shell using:
LANGSMITH_TRACING, LANGSMITH_ENDPOINT, LANGSMITH_AGENT_ID,
LANGSMITH_AGENT_ENVIRONMENT, and LANGSMITH_API_KEY.
Enter the key securely; never store credentials in Git.

Check imports and prompt loading without inference:
    .\.venv\Scripts\python.exe eaios_bedrock_lab.py --prompt v2 --check

Run one investigation:
    .\.venv\Scripts\python.exe eaios_bedrock_lab.py --prompt v1
    .\.venv\Scripts\python.exe eaios_bedrock_lab.py --prompt v2

Application code selects MCP tools, retrieves historical synthetic telemetry,
and supplies it to Nova Micro. LangSmith traces retrieval and generation.
Model-driven tool selection and vector retrieval are not implemented.

## Security checks demonstrated

- Unauthorized read: tool error with no telemetry returned.
- Investigator read: evidence returned.
- L1 restart with recognized approval: DENIED.
- L2 restart without approval: BLOCKED.
- L2 restart with matching fixture: SIMULATED_SUCCESS.
- No real restart executes.

Roles use local process configuration, not real authentication.
Approval is a predefined fixture without expiry or replay protection.
The full L1 validation workflow is not implemented.
Initial AWS testing used a broad role; least-privilege access remains future work.

## Manual evaluation: 2026-10-19

Original prompt, one observed run:
- Source supplied connector active connections as 98 count.
- Model cited the source but reported 98%.
- Model suggested a restart benefit unsupported by supplied evidence.

Revised prompt, one observed run:
- Preserved 98 count.
- Stated that supplied evidence did not support a restart recommendation.
- Preserved unknown gateway health and required human approval.

Both Python responses ended with end_turn.
One improved run does not establish reliability or prove causality.
Next: repeated evaluations and more precise incident-window diagnostic checks.

Successful execution and valid citations do not guarantee faithful output.
A successful wrapper trace does not establish authorization.

## Scope

Learning and interview preparation with synthetic data.
No live database access or autonomous remediation.
