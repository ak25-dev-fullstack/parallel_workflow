import asyncio
import json
import os
import time
from datetime import datetime
from agents import (
    call_claude,
    COORDINATOR_SYSTEM,
    COORDINATOR_USER_TEMPLATE,
    SECURITY_REVIEW_SYSTEM,
    SECURITY_REVIEW_WITH_DELEGATION_TEMPLATE,
    CCNA_EXPLAINER_SYSTEM,
    CCNA_EXPLAINER_WITH_DELEGATION_TEMPLATE,
    TROUBLESHOOTING_SYSTEM,
    TROUBLESHOOTING_WITH_DELEGATION_TEMPLATE,
    SYNTHESIS_SYSTEM,
    SYNTHESIS_USER_TEMPLATE,
)


def _parse_delegation(coordinator_text):
    # The system prompt asks for raw JSON, but models sometimes wrap it in a
    # markdown code fence anyway — strip that defensively before parsing so a
    # cosmetic formatting slip doesn't blow up the whole pipeline.
    text = coordinator_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


async def run_coordinator(config_text):
    start_time = time.time()

    # Step 1: coordinator reads the config alone and decides what each worker
    # should focus on. Plain await — the workers depend on this, so it can't
    # run concurrently with them.
    coordinator_prompt = COORDINATOR_USER_TEMPLATE.format(config_text=config_text)
    coordinator_text, coordinator_usage = await call_claude(
        system=COORDINATOR_SYSTEM,
        user_content=coordinator_prompt,
        model="claude-sonnet-5",
    )
    delegation = _parse_delegation(coordinator_text)

    # Step 2: build each worker's prompt using the coordinator's per-worker
    # instruction.
    security_prompt = SECURITY_REVIEW_WITH_DELEGATION_TEMPLATE.format(
        config_text=config_text, delegation=delegation["security"]
    )
    ccna_prompt = CCNA_EXPLAINER_WITH_DELEGATION_TEMPLATE.format(
        config_text=config_text, delegation=delegation["ccna"]
    )
    troubleshooting_prompt = TROUBLESHOOTING_WITH_DELEGATION_TEMPLATE.format(
        config_text=config_text, delegation=delegation["troubleshooting"]
    )

    # Step 3: the three workers run concurrently — no worker waits on another
    # worker's output, only on the coordinator's already-finished instructions.
    (
        (security_text, security_usage),
        (ccna_text, ccna_usage),
        (troubleshooting_text, troubleshooting_usage),
    ) = await asyncio.gather(
        call_claude(
            system=SECURITY_REVIEW_SYSTEM,
            user_content=security_prompt,
            model="claude-sonnet-5",
        ),
        call_claude(
            system=CCNA_EXPLAINER_SYSTEM,
            user_content=ccna_prompt,
            model="claude-sonnet-5",
        ),
        call_claude(
            system=TROUBLESHOOTING_SYSTEM,
            user_content=troubleshooting_prompt,
            model="claude-sonnet-5",
        ),
    )

    # Step 4: synthesis merges all three worker outputs. Plain await — depends
    # on all three, so it can't start until gather() above completes.
    synthesis_prompt = SYNTHESIS_USER_TEMPLATE.format(
        security_text=security_text,
        troubleshooting_text=troubleshooting_text,
        ccna_text=ccna_text,
    )
    synthesis_text, synthesis_usage = await call_claude(
        system=SYNTHESIS_SYSTEM,
        user_content=synthesis_prompt,
        model="claude-sonnet-5",
        max_tokens=8192,
    )

    elapsed = time.time() - start_time
    total_tokens = (
        coordinator_usage.input_tokens + coordinator_usage.output_tokens
        + security_usage.input_tokens + security_usage.output_tokens
        + ccna_usage.input_tokens + ccna_usage.output_tokens
        + troubleshooting_usage.input_tokens + troubleshooting_usage.output_tokens
        + synthesis_usage.input_tokens + synthesis_usage.output_tokens
    )

    return {
        "delegation": {
            "text": coordinator_text,
            "usage": coordinator_usage,
        },
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
        "synthesis": {
            "text": synthesis_text,
            "usage": synthesis_usage,
        },
        "summary": {
            "elapsed_time": elapsed,
            "total_tokens": total_tokens,
        },
    }


def format_report(result):
    return (
        "=== COORDINATOR DELEGATION PLAN ===\n"
        f"{result['delegation']['text']}\n"
        "\n=== SYNTHESIZED REPORT ===\n"
        f"{result['synthesis']['text']}\n"
        "\n=== RAW SECURITY REVIEW ===\n"
        f"{result['security_review']['text']}\n"
        "\n=== RAW CCNA EXPLAINER ===\n"
        f"{result['ccna_explainer']['text']}\n"
        "\n=== RAW TROUBLESHOOTING ===\n"
        f"{result['troubleshooting']['text']}\n"
        f"\n--- elapsed: {result['summary']['elapsed_time']:.2f}s, "
        f"total tokens: {result['summary']['total_tokens']}\n"
    )


def main():
    with open("sample_configs/basic_router.cfg") as f:
        config_text = f.read()

    result = asyncio.run(run_coordinator(config_text))
    report = format_report(result)
    print(report)

    os.makedirs("results", exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_path = os.path.join("results", f"coordinator_{timestamp}.txt")
    with open(out_path, "w") as f:
        f.write(report)
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
