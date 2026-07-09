# Serverless RAG Chatbot on AWS

A retrieval-augmented generation (RAG) chatbot built entirely on serverless AWS services. Upload a document, ask questions about it, get answers grounded in the document content — no infrastructure to manage.

## Architecture

**Ingest pipeline**
```
S3 (document upload) → Lambda (chunk + embed) → Bedrock (Titan Embeddings) → OpenSearch Serverless (vector store)
```

**Query pipeline**
```
API Gateway → Lambda (query handler) → Bedrock (embed question) → OpenSearch (similarity search) → Bedrock (Nova Lite LLM) → grounded answer
```

Both Lambda functions emit logs and metrics to CloudWatch, with a dashboard tracking invocations, duration, and errors, plus an alarm on high query latency.

## Tech stack and design decisions

| Component | Choice | Why |
|---|---|---|
| Compute | AWS Lambda | Event-driven, pay-per-invocation, zero idle cost — ideal for sporadic document uploads and chat queries. No always-on server needed for this workload. |
| Vector store | OpenSearch Serverless | Managed vector search with k-NN support, no cluster sizing/patching. Serverless billing matches the low, spiky traffic of a demo/personal project. |
| LLM + embeddings | Amazon Bedrock | Managed access to foundation models (Titan Embeddings, Nova Lite) via a single API — no model hosting, no GPU provisioning. Chosen over SageMaker since the goal is to *consume* a foundation model, not train a custom one. |
| API layer | API Gateway (HTTP API) | Lightweight, cheap way to expose the query Lambda over HTTPS without managing a web server. |
| Monitoring | CloudWatch | Native integration with Lambda — logs, invocation count, duration, and error rate available with no extra setup. |
| IAM | Least-privilege roles per Lambda | Ingest role only gets S3 read + Bedrock invoke + OpenSearch write; query role only gets Bedrock invoke + OpenSearch read/write. No shared over-privileged role. |

## Why not other options

- **EC2 instead of Lambda** — would mean paying for idle compute between uploads/queries; not justified at this traffic volume.
- **Self-managed OpenSearch cluster** — requires capacity planning, patching, and scaling decisions that add operational overhead with no benefit at small scale.
- **SageMaker-hosted LLM instead of Bedrock** — would require provisioning and paying for a GPU endpoint continuously; Bedrock's pay-per-token model fits a low-traffic RAG use case better.

## Setup

This project was provisioned via the AWS Console (see `docs/setup-guide.md` for the full click-through steps). At a high level:

1. Create an S3 bucket for document uploads.
2. Create an OpenSearch Serverless collection (vector search type) with encryption, network, and data access policies.
3. Create an IAM role for the ingest Lambda (S3 read, Bedrock invoke, OpenSearch API access).
4. Create the ingest Lambda (`lambda/ingest_handler.py`), attach an `opensearch-py` Lambda layer, and trigger it on S3 object-created events.
5. Create an IAM role for the query Lambda (Bedrock invoke, OpenSearch API access).
6. Create the query Lambda (`lambda/query_handler.py`) with the same layer attached.
7. Expose the query Lambda through an API Gateway HTTP API (`POST /query`).
8. Set up a CloudWatch dashboard and a latency alarm for both functions.

## Usage

Upload a `.txt` document to the S3 bucket — it gets automatically chunked, embedded, and indexed.

Query it:
```bash
curl -X POST https://YOUR_API_ID.execute-api.REGION.amazonaws.com/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is AWS Lambda?"}'
```

Response:
```json
{
  "answer": "AWS Lambda is a serverless compute service that lets you run code without provisioning or managing servers...",
  "sources": ["... retrieved context chunks used to ground the answer ..."]
}
```

## Cost note

OpenSearch Serverless is the main cost driver in this stack (billed for provisioned OCUs even at rest). Delete the collection when not actively demoing to avoid ongoing charges. Lambda, S3, and Bedrock are all pay-per-use with no idle cost.

## Possible extensions

- Add DynamoDB to persist chat history per session.
- Add Bedrock Guardrails for content filtering on responses.
- Support PDF/DOCX ingestion instead of plain text.
- Add a simple frontend (static S3 site) to replace curl-based testing.
