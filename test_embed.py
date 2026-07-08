import asyncio
from app.core.llm.embeddings import get_embeddings_client
async def main():
    try:
        client = get_embeddings_client()
        res = await client.aembed_query("test query")
        print("Success! Dimensions:", len(res))
    except Exception as e:
        print("Error:", e)
asyncio.run(main())
