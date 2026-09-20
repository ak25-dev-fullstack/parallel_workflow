import os
from dotenv import load_dotenv
import anthropic

load_dotenv()  # reads .env into environment variables

client = anthropic.Anthropic()  # auto-reads ANTHROPIC_API_KEY from the environment

response = client.messages.create(
    model="claude-sonnet-5",
    max_tokens=100,
    messages=[{"role": "user", "content": "Say hello in one sentence."}],
)

for block in response.content:
    if block.type == "text":
        print(block.text)