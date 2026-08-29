# Argus — Challenges Faced & Lessons Learned

Real issues hit during the build and deployment of Argus (local → ECS Fargate),
with root causes and fixes. Kept as an engineering log — and as interview material,
because the debugging is the story.

---

## 1. Config not loading — `.env` in the wrong directory
**Symptom:** App crashed at startup with `OpenAIError: Missing credentials` even though
`LLM_PROVIDER=bedrock` was set.
**Root cause:** The `.env` file had been saved into `tests/` instead of the project root.
`pydantic-settings` loads `.env` relative to the working directory, so none of the
config was seen and the app fell back to the OpenAI default.
**Fix:** Moved `.env` to the project root. Also added `load_dotenv()` at the top of
`app.py` so variables land in `os.environ` — required because LangSmith and boto3 read
the process environment directly, not pydantic settings.
**Lesson:** Two config consumers (pydantic vs. os.environ) means one `.env` must feed both.

## 2. Bedrock API key under the wrong variable name
**Symptom:** Bedrock auth ignored despite a valid API key in `.env`.
**Root cause:** The key was stored as `BEDROCK_API_KEY`, a name nothing reads.
boto3 expects the Bedrock long-term API key as `AWS_BEARER_TOKEN_BEDROCK`.
**Fix:** Renamed the variable (standard AWS CLI credentials also work with zero config).
**Lesson:** Env var contracts are exact; "close enough" names fail silently.

## 3. `ChatBedrockConverse` rejected the model ARN
**Symptom:** `ValidationError: Model provider should be supplied when passing a model ARN`.
**Root cause:** With a full inference-profile ARN, LangChain cannot infer the provider
from the string.
**Fix:** Switched to the plain inference profile ID
(`us.anthropic.claude-3-5-sonnet-...`) — shorter, portable across accounts, and no
account ID leaked into a public repo. (Alternative: keep the ARN and pass `provider="anthropic"`.)

## 4. Bedrock `AccessDeniedException` — account under verification
**Symptom:** First end-to-end request failed with "Your account is currently being verified."
**Root cause:** New AWS accounts go through automated verification before Bedrock
invocation is allowed. Not a config error; nothing to fix.
**Fix:** Waited (~2 hours max). Separately confirmed model access was granted in the
Bedrock console for the working region — a second, independent gate.
**Lesson:** Distinguish "my config is wrong" from "the platform is gating me" before
touching anything.

## 5. Truncated Google Drive folder ID
**Symptom:** Drive search failed with "parent folder can't be found."
**Root cause:** One folder ID had been partially copied from the URL (missing its
leading characters). Drive treats an unknown parent in `'<id>' in parents` as nonexistent.
**Fix:** Wrote a 20-line verification script that authenticates as the service account
and calls `files().get()` on each configured folder ID, printing OK/BROKEN per ID.
Re-copied the broken ID.
**Lesson:** When an integration spans identity + config, test each ID *as the service
identity*, not as yourself. Small verification scripts pay for themselves instantly.

## 6. Least-privilege sharing
**Issue:** Drive folder initially shared with the service account as Editor.
**Fix:** Downgraded to Viewer. Defense in depth: the OAuth scope is `drive.readonly`
anyway, so writes were impossible — but scope-level AND share-level restriction is the
right posture, and a good governance talking point.

## 7. Region mismatch — secrets, cluster, and image in different regions
**Symptom:** ECS tasks died with `ResourceInitializationError: invalid ssm parameters`.
**Root cause:** Deploy scripts defaulted to `us-east-1` while interactive work (and
Bedrock access) was in `us-east-2`. SSM parameters, the ECS cluster, ECR image, and the
task definition's hardcoded regions were split across regions. ECS reports a
parameter that exists in another region as simply "invalid."
**Fix:** Standardized everything on one region: exported `AWS_REGION=us-east-2`, re-ran
the (idempotent) secrets and deploy scripts, and fixed the two hardcoded regions in the
task definition.
**Lesson:** "Invalid parameter" usually means "wrong region," not "wrong value."
Idempotent deploy scripts made re-running in the right region painless.

## 8. One secret never reached Parameter Store (`GOOGLE_SA_JSON`)
**Symptom:** After the region fix, tasks still failed — but now naming exactly one
parameter: `/argus/GOOGLE_SA_JSON`.
**Root cause:** The secrets script read the service-account JSON via
`$(cat ../service-account.json)`; the relative path was wrong at run time, so that one
`put-parameter` call failed while the other four succeeded — easy to miss in scroll-by.
**Fix:** Re-created the parameter with `--value file://service-account.json` (no shell
interpolation), then verified round-trip integrity by pulling it back and piping through
`json.load` before redeploying.
**Lesson:** Prefer `file://` over `$(cat ...)` for multi-line secrets; always verify a
secret can be read back as valid JSON before blaming the consumer.

## 9. Agent couldn't act on "this channel" — missing situational context
**Symptom:** In Slack: "It seems I don't have access to this channel or the channel ID
is incorrect" — even though the bot was a channel member.
**Root cause:** A context-engineering gap, not a permissions bug. The Slack event
carries the channel ID, but only the raw user text was passed to the agent — so when the
user said "this channel," the LLM had no idea where "here" was and guessed an ID.
**Fix:** Injected conversation context into the agent input ("this conversation is in
channel id C0123..."), and added a channel name→ID resolver so "#general" works too
(required the `groups:read` scope + Slack app reinstall).
**Lesson:** Agents fail without the situational context humans get for free. The fix was
prompt/context engineering, not tools — a recurring pattern in agent debugging.

## 10. Socket Mode: local and ECS instances competing
**Symptom:** After ECS deploy, Slack responses became intermittent.
**Root cause:** The local dev instance was still running; two Socket Mode consumers on
the same app token split the event stream between them.
**Fix:** Stop the local instance whenever the ECS service is live (and vice versa for
local debugging).
**Lesson:** Socket Mode is effectively single-consumer for this design — the deployment
model must account for it.

## 11. PDFs unreadable from Drive
**Symptom:** Agent reported PDFs as unsupported.
**Root cause:** The read tool only handled Google-native exports and text files; PDFs
download as binary.
**Fix:** Added `pypdf` text extraction (first 30 pages, char-capped), a graceful message
for scanned/no-text-layer PDFs, and — critically — updated the tool's **docstring**, since
the LLM decides what a tool can do from its description.
**Lesson:** For agent tools, the docstring is part of the API surface. Code that works
but is described wrongly will never be called correctly.
