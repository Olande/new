import asyncio
from app.core.llm.embeddings import get_embeddings_client
import math

def cosine_similarity(v1, v2):
    dot_product = sum(a*b for a,b in zip(v1, v2))
    norm_v1 = math.sqrt(sum(a*a for a in v1))
    norm_v2 = math.sqrt(sum(a*a for a in v2))
    return dot_product / (norm_v1 * norm_v2)

def cosine_distance(v1, v2):
    return 1 - cosine_similarity(v1, v2)

async def main():
    try:
        client = get_embeddings_client()
        v1 = await client.aembed_query("software engineer python")
        v2 = await client.aembed_query("experienced python developer working on backend systems")
        v3 = await client.aembed_query("senior software engineer role using python and django")
        v4 = await client.aembed_query("cashier at a grocery store")

        print("Distance 1-2:", cosine_distance(v1, v2))
        print("Distance 1-3:", cosine_distance(v1, v3))
        print("Distance 1-4:", cosine_distance(v1, v4))
    except Exception as e:
        print("Error:", e)

asyncio.run(main())
