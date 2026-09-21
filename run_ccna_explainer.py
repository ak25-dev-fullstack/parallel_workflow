import asyncio
from agents import call_claude, CCNA_EXPLAINER_SYSTEM, CCNA_EXPLAINER_USER_TEMPLATE


async def main():
    with open("sample_configs/basic_router.cfg") as f:
        config_text = f.read()

    user_prompt = CCNA_EXPLAINER_USER_TEMPLATE.format(config_text=config_text)

    text, usage = await call_claude(
        system=CCNA_EXPLAINER_SYSTEM,
        user_content=user_prompt,
        model="claude-sonnet-5",
    )

    print(text)
    print(f"\n--- tokens: {usage.input_tokens} in {usage.output_tokens} out")

asyncio.run(main())
