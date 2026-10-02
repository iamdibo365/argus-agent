# Argus — AI Agent for Slack + Google Drive on AWS

Argus is a production single AI agent that lives in your Slack workspace and can
search and read your Google Drive, summarize channel discussions, and post messages —
built with **LangChain / LangGraph**, **OpenAI** (or **AWS Bedrock** via one env var),
**LangSmith** tracing, and deployed as a container on **AWS ECS Fargate**.

> Roadmap: Argus v2 evolves into a multi-agent team (researcher, writer, reviewer)
> orchestrated with LangGraph — this repo is the single-agent foundation.

## Architecture

```
Slack (Socket Mode websocket)
        │
        ▼
┌─────────────────────────────┐
│  ECS Fargate container       │
│  ┌────────────────────────┐  │        ┌──────────────┐
│  │ Slack Bolt app          │  │◄──────►│  LangSmith   │ (tracing)
│  │   └─ LangGraph ReAct    │  │        └──────────────┘
│  │      agent              │  │
│  │   Tools:                │  │        ┌──────────────┐
│  │   • search_drive        │──┼───────►│ Google Drive │
│  │   • read_drive_file     │  │        └──────────────┘
│  │   • send_slack_message  │  │        ┌──────────────┐
│  │   • get_channel_history │──┼───────►│  Slack API   │
│  └────────────────────────┘  │        └──────────────┘
│  LLM: OpenAI GPT-4o  ⇄  AWS Bedrock (Claude) — env var swap
└─────────────────────────────┘
   Secrets: SSM Parameter Store · Logs: CloudWatch
```

**Why Socket Mode?** The container connects *out* to Slack over a websocket, so there is
no public endpoint, no API Gateway, and no ALB — smaller attack surface, simpler infra,
and no Slack 3-second-ack gymnastics.

## Project structure

```
argus-agent/
├── README.md
├── .env.example
├── .gitignore
├── requirements.txt
├── Dockerfile
├── src/argus/
│   ├── __init__.py
│   ├── config.py           # pydantic-settings config
│   ├── llm.py              # OpenAI ⇄ Bedrock factory
│   ├── agent.py            # LangGraph ReAct agent + per-thread memory
│   ├── app.py              # Slack Bolt (Socket Mode) entrypoint
│   └── tools/
│       ├── drive_tools.py  # search_drive, read_drive_file
│       └── slack_tools.py  # send_slack_message, get_channel_history
├── deploy/
│   ├── put_secrets.sh      # push secrets to SSM Parameter Store
│   ├── ecr_push.sh         # build + push Docker image to ECR
│   ├── ecs_task_def.json   # Fargate task definition (secrets from SSM)
│   └── deploy_ecs.sh       # IAM roles, cluster, service — full deploy
└── tests/
    └── test_agent.py
```

---

## Step-by-step setup

### Step 1 — Create the Slack app
1. Go to https://api.slack.com/apps → **Create New App** → *From scratch* → name it **Argus**.
2. **Socket Mode** (left sidebar) → enable it → generate an **App-Level Token** with scope
   `connections:write` → save as `SLACK_APP_TOKEN` (`xapp-...`).
3. **OAuth & Permissions** → add Bot Token Scopes:
   `app_mentions:read`, `chat:write`, `channels:history`, `channels:read`, `groups:history`, `im:history`, `im:read`, `im:write`
4. **Event Subscriptions** → enable → subscribe to bot events: `app_mention`, `message.im`.
5. **Install to Workspace** → copy the **Bot User OAuth Token** as `SLACK_BOT_TOKEN` (`xoxb-...`).
6. In Slack, `/invite @Argus` to any channel you want it to read.

### Step 2 — Create the Google service account
1. https://console.cloud.google.com → create/select a project → **APIs & Services** →
   enable the **Google Drive API**.
2. **IAM & Admin → Service Accounts** → create `argus-agent` → **Keys** → add a JSON key →
   download it as `service-account.json` into the repo root (it's gitignored).
3. In Google Drive, **share the folder(s)** you want Argus to see with the service
   account's email (`argus-agent@<project>.iam.gserviceaccount.com`) as Viewer.
4. (Optional) Put a folder id in `GOOGLE_DRIVE_FOLDER_ID` to scope searches.

### Step 3 — LangSmith
1. https://smith.langchain.com → Settings → create an API key → `LANGSMITH_API_KEY`.
2. Tracing is enabled purely by env vars (`LANGSMITH_TRACING=true`) — no code changes.

### Step 4 — (Optional) AWS Bedrock
1. AWS Console → Bedrock → **Model access** → request access to Anthropic Claude models
   in your region.
2. Set `LLM_PROVIDER=bedrock`. Locally you need AWS credentials; on ECS the task role
   already has `bedrock:InvokeModel`.

### Step 5 — Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # fill in your values
PYTHONPATH=src python -m argus.app
```
Then in Slack: `@Argus what files do we have about Q3 planning?` or DM it directly.
Watch the full trace appear in LangSmith.

### Step 6 — Deploy to AWS (ECS Fargate)
Prereqs: AWS CLI configured, Docker running.
```bash
cd deploy
bash put_secrets.sh      # after editing in your real secret values
bash ecr_push.sh         # build + push image to ECR
bash deploy_ecs.sh       # IAM roles, cluster, task def, service
aws logs tail /ecs/argus-agent --follow
```
Redeploy after code changes: `bash ecr_push.sh && bash deploy_ecs.sh` (forces a new deployment).

---

## Demo script (for LinkedIn / interviews)
1. `@Argus summarize the last 20 messages in this channel` → Slack history tool.
2. `@Argus find our AI governance checklist in Drive and give me the top 5 items` →
   Drive search + read, with the file name cited.
3. `@Argus post a one-line status update to #general` → cross-channel action.
4. Show the LangSmith trace tree: LLM reasoning → tool calls → final answer.
5. Flip `LLM_PROVIDER=bedrock`, redeploy, run the same demo — provider-agnostic agent.

## Cost notes
- Fargate 0.5 vCPU / 1 GB ≈ $18/mo if left running 24/7 — set desired-count to 0 when
  not demoing: `aws ecs update-service --cluster argus-cluster --service argus-service --desired-count 0`
- LLM cost is per-call; GPT-4o or Claude on Bedrock at demo volume is a few dollars.

## Roadmap → multi-agent (v2)
- Split into researcher / writer / reviewer agents with a LangGraph supervisor graph.
- Swap `MemorySaver` for a DynamoDB/Postgres checkpointer.
- Add human-in-the-loop approval before any `send_slack_message` to other channels.
