import json
import boto3
import re
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

REGION = "ap-south-2"
OPENSEARCH_HOST = "7ckvndbr0f3y9bt0ewb7.aoss.ap-south-2.on.aws"
INDEX_NAME = "rag-index"
BEDROCK_REGION = "ap-south-1"

s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)

session = boto3.Session()
credentials = session.get_credentials()
auth = AWSV4SignerAuth(credentials, REGION, "aoss")

client = OpenSearch(
    hosts=[{"host": OPENSEARCH_HOST, "port": 443}],
    http_auth=auth,
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection,
    timeout=30,
    max_retries=3,
    retry_on_timeout=True,
    http_compress=True
)


def chunk_text(text, chunk_size=500):
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size):
        chunks.append(" ".join(words[i:i + chunk_size]))
    return chunks


def get_embedding(text):
    body = json.dumps({"inputText": text})
    response = bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=body,
        contentType="application/json",
        accept="application/json"
    )
    result = json.loads(response["body"].read())
    return result["embedding"]


def ensure_index():
    if not client.indices.exists(index=INDEX_NAME):
        index_body = {
            "settings": {"index.knn": True},
            "mappings": {
                "properties": {
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": 1024
                    },
                    "text": {"type": "text"}
                }
            }
        }
        client.indices.create(index=INDEX_NAME, body=index_body)


def lambda_handler(event, context):
    ensure_index()

    bucket = event["Records"][0]["s3"]["bucket"]["name"]
    key = event["Records"][0]["s3"]["object"]["key"]

    obj = s3.get_object(Bucket=bucket, Key=key)
    raw_text = obj["Body"].read().decode("utf-8")
    raw_text = re.sub(r"\s+", " ", raw_text)

    chunks = chunk_text(raw_text)

    for idx, chunk in enumerate(chunks):
        embedding = get_embedding(chunk)
        doc = {"text": chunk, "embedding": embedding}
        client.index(index=INDEX_NAME, body=doc, id=f"{key}-{idx}")

    print(f"Indexed {len(chunks)} chunks from {key}")

    return {"statusCode": 200, "body": f"Indexed {len(chunks)} chunks from {key}"}