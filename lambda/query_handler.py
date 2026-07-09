import json
import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

REGION = "ap-south-2"
OPENSEARCH_HOST = "7ckvndbr0f3y9bt0ewb7.aoss.ap-south-2.on.aws"
INDEX_NAME = "rag-index"
BEDROCK_REGION = "ap-south-1"

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


def search_similar_chunks(query_embedding, k=3):
    search_body = {
        "size": k,
        "query": {
            "knn": {
                "embedding": {
                    "vector": query_embedding,
                    "k": k
                }
            }
        }
    }
    response = client.search(index=INDEX_NAME, body=search_body)
    hits = response["hits"]["hits"]
    return [hit["_source"]["text"] for hit in hits]


def ask_llm(question, context_chunks):
    context = "\n\n".join(context_chunks)
    prompt = f"""Answer the question using only the context below. If the answer isn't in the context, say you don't know.

Context:
{context}

Question: {question}

Answer:"""

    body = json.dumps({
        "messages": [
            {"role": "user", "content": [{"text": prompt}]}
        ],
        "inferenceConfig": {
            "maxTokens": 500,
            "temperature": 0.3
        }
    })

    response = bedrock.invoke_model(
        modelId="apac.amazon.nova-lite-v1:0",
        body=body,
        contentType="application/json",
        accept="application/json"
    )
    result = json.loads(response["body"].read())
    return result["output"]["message"]["content"][0]["text"]


def lambda_handler(event, context):
    body = json.loads(event.get("body", "{}"))
    question = body.get("question", "")

    if not question:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "question is required"})
        }

    query_embedding = get_embedding(question)
    context_chunks = search_similar_chunks(query_embedding)
    answer = ask_llm(question, context_chunks)

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"answer": answer, "sources": context_chunks})
    }