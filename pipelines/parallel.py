import asyncio
import os
import time
from datetime import datetime
from agents import call_claude, SECURITY_REVIEW_SYSTEM, SECURITY_REVIEW_USER_TEMPLATE, CCNA_EXPLAINER_SYSTEM, CCNA_EXPLAINER_USER_TEMPLATE, TROUBLESHOOTING_SYSTEM, TROUBLESHOOTING_USER_TEMPLATE

async def run_parallel(config_text):

    # Prepare prompts for each agent
    security_review_prompt = SECURITY_REVIEW_USER_TEMPLATE.format(config_text=config_text)
    ccna_explainer_prompt = CCNA_EXPLAINER_USER_TEMPLATE.format(config_text=config_text)
    troubleshooting_prompt = TROUBLESHOOTING_USER_TEMPLATE.format(config_text=config_text)

    start_time = time.time()

    # No await here — these are coroutine objects, not yet running. gather()
    # schedules all three on the event loop together instead of one at a time.
    (security_text, security_usage), (ccna_text, ccna_usage), (troubleshooting_text, troubleshooting_usage) = await asyncio.gather(
        call_claude(
            system=SECURITY_REVIEW_SYSTEM,
            user_content=security_review_prompt,
            model="claude-sonnet-5",
        ),
        call_claude(
            system=CCNA_EXPLAINER_SYSTEM,
            user_content=ccna_explainer_prompt,
            model="claude-sonnet-5",
        ),
        call_claude(
            system=TROUBLESHOOTING_SYSTEM,
            user_content=troubleshooting_prompt,
            model="claude-sonnet-5",
        ),
    )

    elapsed = time.time() - start_time
    total_tokens = (
        security_usage.input_tokens + security_usage.output_tokens
        + ccna_usage.input_tokens + ccna_usage.output_tokens
        + troubleshooting_usage.input_tokens + troubleshooting_usage.output_tokens
    )

    return {
        "security_review": {
            "text": security_text,
            "usage": security_usage,
        },
        "ccna_explainer": {
            "text": ccna_text,
            "usage": ccna_usage,
        },
        "troubleshooting": {
            "text": troubleshooting_text,
            "usage": troubleshooting_usage,
        },
        "summary":{
            "elapsed_time": elapsed,
            "total_tokens": total_tokens,
        }
    }


def format_report(result):
    return (
        "=== SECURITY REVIEW ===\n"
        f"{result['security_review']['text']}\n"
        "\n=== CCNA EXPLAINER ===\n"
        f"{result['ccna_explainer']['text']}\n"
        "\n=== TROUBLESHOOTING ===\n"
        f"{result['troubleshooting']['text']}\n"
        f"\n--- elapsed: {result['summary']['elapsed_time']:.2f}s, "
        f"total tokens: {result['summary']['total_tokens']}\n"
    )


def main():
    with open("sample_configs/basic_router.cfg") as f:
        config_text = f.read()

    result = asyncio.run(run_parallel(config_text))
    report = format_report(result)
    print(report)

    os.makedirs("results", exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_path = os.path.join("results", f"parallel_{timestamp}.txt")
    with open(out_path, "w") as f:
        f.write(report)
    print(f"Saved to {out_path}")

if __name__ == "__main__":
    main()

