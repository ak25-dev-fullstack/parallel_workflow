import asyncio
from pipelines.sequential import run_sequential
from pipelines.parallel import run_parallel
from pipelines.coordinator import run_coordinator


def _token_breakdown(result):
    call_keys = [k for k in result if k != "summary"]
    input_tokens = sum(result[k]["usage"].input_tokens for k in call_keys)
    output_tokens = sum(result[k]["usage"].output_tokens for k in call_keys)
    return len(call_keys), input_tokens, output_tokens


async def run_all(config_text):
    print("Running sequential...")
    sequential_result = await run_sequential(config_text)

    print("Running parallel...")
    parallel_result = await run_parallel(config_text)

    print("Running coordinator...")
    coordinator_result = await run_coordinator(config_text)

    return sequential_result, parallel_result, coordinator_result


def print_comparison(results):
    header = (
        f"{'pipeline':<12} {'calls':>5} {'elapsed (s)':>12} "
        f"{'in tokens':>10} {'out tokens':>11} {'total tokens':>13}"
    )
    print(header)
    print("-" * len(header))

    rows = []
    for name, result in results:
        num_calls, in_tok, out_tok = _token_breakdown(result)
        elapsed = result["summary"]["elapsed_time"]
        total = result["summary"]["total_tokens"]
        rows.append((name, num_calls, elapsed, in_tok, out_tok, total))
        print(f"{name:<12} {num_calls:>5} {elapsed:>12.2f} {in_tok:>10} {out_tok:>11} {total:>13}")

    seq = next(r for r in rows if r[0] == "sequential")
    par = next(r for r in rows if r[0] == "parallel")
    coord = next(r for r in rows if r[0] == "coordinator")

    speedup = seq[2] / par[2] if par[2] else float("inf")
    coord_extra_time = coord[2] - par[2]
    coord_extra_tokens = coord[5] - par[5]

    print(
        f"\nParallel was {speedup:.2f}x faster than sequential "
        f"({seq[2]:.2f}s -> {par[2]:.2f}s) for the same 3 concerns.\n"
        f"Coordinator added {coord[1] - par[1]} extra calls (delegation + synthesis), "
        f"costing {coord_extra_time:.2f}s and {coord_extra_tokens} tokens more than parallel, "
        f"in exchange for per-worker instructions tailored to this specific config and one "
        f"merged, prioritized report instead of three separate ones."
    )


def main():
    with open("sample_configs/basic_router.cfg") as f:
        config_text = f.read()

    sequential_result, parallel_result, coordinator_result = asyncio.run(run_all(config_text))
    print_comparison(
        [
            ("sequential", sequential_result),
            ("parallel", parallel_result),
            ("coordinator", coordinator_result),
        ]
    )


if __name__ == "__main__":
    main()
