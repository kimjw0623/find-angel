import discord
from discord_webhook import DiscordWebhook
import asyncio
import aiohttp
import dotenv
import os

# 사용 예시
if __name__ == "__main__":
    # Discord 채널의 웹훅 URL을 넣으세요
    dotenv.load_dotenv()
    webhook_url = os.getenv('WEBHOOK')

    webhook = DiscordWebhook(url=webhook_url, content="테스트")
    response = webhook.execute()