# Setup guide — console steps

This project was built via the AWS Console. Steps below reproduce it end to end.

## 1. S3 bucket

1. **S3 → Create bucket**
2. Name it (globally unique), pick a region, keep "Block all public access" checked.
3. Create.

## 2. IAM role for ingest Lambda

1. **IAM → Roles → Create role → AWS service → Lambda**
2. Name: `rag-ingest-lambda-role`
3. Attach inline policy granting:
   - `s3:GetObject` on the bucket
   - `bedrock:InvokeModel`
4. Attach managed policy `AWSLambdaBasicExecutionRole` (for CloudWatch logging).

## 3. OpenSearch Serverless collection

1. **OpenSearch Service → Serverless → Collections → Create collection**
2. Type: **Vector search**. Use **Standard create** (Easy create's auto-principal can be invalid for cross-account/console setups).
3. Create an **encryption policy** (AWS owned key is fine for a demo).
4. Create a **network policy** — Public access for a learning project (tighten for production).
5. Create a **data access policy** granting index-level permissions (create, read, write, delete, describe) on the collection, with principals set to:
   - Your IAM user (for testing from console/CloudShell)
   - `rag-ingest-lambda-role`
   - `rag-query-lambda-role` (added once that role exists)
6. Note the OpenSearch endpoint once the collection is **Active**.

**Important**: the data access policy grants access to the *index*, but the Lambda execution role also needs an IAM permission for `aoss:APIAccessAll` — add this as an inline policy on both Lambda roles, or requests will fail with a 403 even though the data access policy looks correct.

## 4. Ingest Lambda

1. **Lambda → Create function → Author from scratch**
2. Name: `rag-ingest-handler`, runtime Python 3.12, execution role = `rag-ingest-lambda-role`.
3. Paste `lambda/ingest_handler.py` content, **Deploy**.
4. Add a Lambda layer bundling `opensearch-py` (build via AWS CloudShell: `pip install opensearch-py -t python/ && zip -r layer.zip python`, upload as a layer, attach it).
5. Add trigger: S3 → your bucket → event type `PUT` / `ObjectCreated:*`.
6. Bump **Configuration → General configuration**: memory 512 MB, timeout 60–120s (default 128 MB / 3s is too small for embedding calls).
7. Test by uploading a `.txt` file to the bucket, then check `/aws/lambda/rag-ingest-handler` in CloudWatch Logs.

## 5. IAM role for query Lambda

1. Same pattern as ingest role, but permissions: `bedrock:InvokeModel` + `aoss:APIAccessAll`.
2. Attach `AWSLambdaBasicExecutionRole` too.
3. Add this role's ARN to the OpenSearch data access policy from step 3.

## 6. Query Lambda

1. Create `rag-query-handler`, Python 3.12, execution role = `rag-query-lambda-role`.
2. Paste `lambda/query_handler.py`, attach the same OpenSearch layer, **Deploy**.
3. Same memory/timeout bump as the ingest function.

## 7. API Gateway

1. **API Gateway → Create API → HTTP API**
2. Add integration: Lambda → `rag-query-handler`.
3. Route: `POST /query`.
4. Default stage with auto-deploy.
5. Test with:
   ```bash
   curl -X POST https://YOUR_API_ID.execute-api.REGION.amazonaws.com/query \
     -H "Content-Type: application/json" \
     -d '{"question": "What is AWS Lambda?"}'
   ```

## 8. Monitoring

1. **CloudWatch → Dashboards → Create dashboard**, add widgets for Invocations, Duration, Errors for both Lambda functions.
2. **CloudWatch → Alarms → Create alarm** on `rag-query-handler` Duration, threshold e.g. 5000 ms, optionally notify via SNS email.

## Notes on model choices

- Some Bedrock model IDs get deprecated over time (e.g. Titan Text Express/Lite reached end of life). If `InvokeModel` returns `ResourceNotFoundException`, check the Bedrock console's current model catalog for a replacement ID.
- Newer models (e.g. Amazon Nova) may require an **inference profile ID** rather than the bare model ID — if you see `ValidationException: ... isn't supported with on-demand throughput`, look up the correct cross-region inference profile ID in **Bedrock → Cross-region inference** for your region.