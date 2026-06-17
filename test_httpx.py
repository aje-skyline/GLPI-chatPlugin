import asyncio
import httpx
from app.config import settings
from app.infrastructure.http_client import get_base_headers

async def main():
    print("Base headers:", get_base_headers())
    api_base = settings.glpi_api_url.rstrip("/")
    print("API Base:", api_base)
    client = httpx.AsyncClient(verify=False)
    headers = {
        **get_base_headers(),
        "Authorization": f"user_token {settings.glpi_user_token}",
    }
    print("Request Headers:", headers)
    resp = await client.get(f"{api_base}/initSession", headers=headers)
    print("Status code:", resp.status_code)
    print("Response text:", resp.text)
    await client.aclose()

asyncio.run(main())
