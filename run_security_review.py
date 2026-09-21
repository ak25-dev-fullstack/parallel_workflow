import asyncio
from agents import call_claude, SECURITY_REVIEW_SYSTEM, SECURITY_REVIEW_USER_TEMPLATE


async def main():
    with open("sample_configs/basic_router.cfg") as f:
        config_text = f.read()

    user_prompt = SECURITY_REVIEW_USER_TEMPLATE.format(config_text=config_text)

    text, usage = await call_claude(
        system=SECURITY_REVIEW_SYSTEM,
        user_content=user_prompt,
        model="claude-sonnet-5",
    )

    print(text)
    print(f"\n--- tokens: {usage.input_tokens} in {usage.output_tokens} out")

asyncio.run(main())