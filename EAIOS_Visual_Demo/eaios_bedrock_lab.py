import argparse
import json
from pathlib import Path

import anyio
import boto3
from langsmith import Client as TraceClient, traceable
from mcp import Client as MCPClient
from eaios_mcp_lab import mcp

BASE = Path(__file__).resolve().parent
tracing = TraceClient(auto_batch_tracing=False)


@traceable(name="MCP payment evidence", client=tracing)
async def collect_evidence():
    evidence = []
    async with MCPClient(mcp) as client:
        for component in [
            "COMP-ORDER-DB",
            "COMP-PAY-CONNECTOR",
            "AS-PAYMENT-GATEWAY",
        ]:
            result = await client.call_tool(
                "get_component_health",
                {"component_id": component},
            )
            if result.is_error:
                raise RuntimeError(
                    "Evidence retrieval failed; generation stopped."
                )
            for block in result.content:
                if block.type == "text":
                    evidence.append(json.loads(block.text))
    return evidence


@traceable(name="Nova Micro investigation brief", run_type="llm", client=tracing)
def generate_brief(evidence, prompt_version, instructions, profile):
    bedrock = boto3.Session(
        profile_name=profile,
        region_name="us-east-2",
    ).client("bedrock-runtime")

    response = bedrock.converse(
        modelId="us.amazon.nova-micro-v1:0",
        system=[{"text": instructions}],
        messages=[{
            "role": "user",
            "content": [{"text": json.dumps(evidence)}],
        }],
        inferenceConfig={"maxTokens": 1024, "temperature": 0.2},
    )
    return {
        "prompt_version": prompt_version,
        "model": "us.amazon.nova-micro-v1:0",
        "brief": "".join(
            block.get("text", "")
            for block in response["output"]["message"]["content"]
        ),
        "stop_reason": response["stopReason"],
        "usage": response["usage"],
    }


@traceable(name="EAIOS MCP to Bedrock investigation", client=tracing)
async def investigate(prompt_version, instructions, profile):
    evidence = await collect_evidence()
    return generate_brief(
        evidence, prompt_version, instructions, profile
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", choices=["v1", "v2"], default="v2")
    parser.add_argument("--profile", default="eaios-learning")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    prompt_path = BASE / "lab_prompts" / f"investigation_{args.prompt}.txt"
    instructions = prompt_path.read_text(encoding="utf-8-sig")

    if args.check:
        print("Imports and prompt file OK:", prompt_path.name)
        print("No AWS inference or MCP tool call performed.")
        return

    result = anyio.run(
        investigate, args.prompt, instructions, args.profile
    )
    print(result["brief"])
    print("\nPrompt:", result["prompt_version"])
    print("Stop reason:", result["stop_reason"])
    print("Token usage:", result["usage"])
    if result["stop_reason"] != "end_turn":
        print("REVIEW REQUIRED: response did not finish with end_turn.")


if __name__ == "__main__":
    main()
