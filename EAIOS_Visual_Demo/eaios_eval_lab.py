import argparse
import hashlib
from pathlib import Path

from langsmith import Client
from lab_evaluators import citation_validity
from eaios_bedrock_lab import generate_brief

BASE = Path(__file__).resolve().parent


def normal_completion(outputs):
    return {
        "key": "normal_completion",
        "score": outputs.get("stop_reason") == "end_turn",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", choices=["v1", "v2"], required=True)
    args = parser.parse_args()

    instructions = (
        BASE / "lab_prompts" / f"investigation_{args.prompt}.txt"
    ).read_text(encoding="utf-8-sig")

    def target(inputs):
        return generate_brief(
            evidence=inputs["evidence"],
            prompt_version=args.prompt,
            instructions=instructions,
            profile="eaios-learning",
        )

    client = Client()
    client.evaluate(
        target,
        data="eaios-payment-evals-v1",
        evaluators=[normal_completion, citation_validity],
        experiment_prefix=f"eaios-payment-{args.prompt}",
        metadata={
            "prompt_version": args.prompt,
            "prompt_sha256": hashlib.sha256(
                instructions.encode("utf-8")
            ).hexdigest(),
            "model": "us.amazon.nova-micro-v1:0",
            "temperature": 0.2,
            "max_tokens": 1024,
        },
        max_concurrency=1,
        num_repetitions=1,
    )
    print("Experiment completed:", args.prompt)


if __name__ == "__main__":
    main()
