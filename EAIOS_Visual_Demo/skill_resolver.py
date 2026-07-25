from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json


@dataclass(frozen=True)
class AgentSelection:
    agent_id: str
    agent_name: str
    assigned_skills: list[str]
    reliability_score: float
    estimated_cost: float
    a2a_protocol: str
    mcp_tools: list[str]
    data_domains: list[str]


@dataclass(frozen=True)
class SkillResolution:
    required_skills: list[str]
    selected_agents: list[AgentSelection]
    uncovered_skills: list[str]
    selection_explanation: str


class SkillResolver:
    """Resolve required skills to a minimal capable active agent set.

    This is a greedy weighted set-cover resolver. Agent count is an outcome of
    registry data, not an orchestration constant.
    """

    def __init__(
        self,
        skill_catalog_file: str | Path,
        agent_registry_file: str | Path,
    ) -> None:
        self.skill_catalog = self._read(Path(skill_catalog_file))
        self.agent_registry = self._read(Path(agent_registry_file))
        self.known_skills = {
            row["skill_id"] for row in self.skill_catalog["skills"]
        }

    @staticmethod
    def _read(path: Path) -> dict:
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def resolve(self, required_skills: list[str]) -> SkillResolution:
        unknown = sorted(set(required_skills) - self.known_skills)
        if unknown:
            raise ValueError(f"Unknown required skills: {unknown}")

        uncovered = set(required_skills)
        available = [
            row for row in self.agent_registry["agents"]
            if row.get("status") == "ACTIVE"
        ]
        selected: list[AgentSelection] = []
        selected_ids: set[str] = set()

        while uncovered:
            candidates = []
            for agent in available:
                if agent["agent_id"] in selected_ids:
                    continue
                coverage = uncovered & set(agent.get("skills", []))
                if not coverage:
                    continue
                reliability = float(agent.get("reliability_score", 0.5))
                cost = max(float(agent.get("estimated_cost", 1.0)), 0.01)
                utility = (
                    len(coverage) * 10.0
                    + reliability
                    - 0.05 * cost
                )
                candidates.append((utility, reliability, -cost, agent["agent_id"], coverage, agent))

            if not candidates:
                break

            _, reliability, negative_cost, _, coverage, agent = max(candidates)
            selected_ids.add(agent["agent_id"])
            assigned = sorted(coverage)
            selected.append(
                AgentSelection(
                    agent_id=agent["agent_id"],
                    agent_name=agent["name"],
                    assigned_skills=assigned,
                    reliability_score=round(reliability, 3),
                    estimated_cost=round(-negative_cost, 3),
                    a2a_protocol=agent.get("a2a_protocol", "UNSPECIFIED"),
                    mcp_tools=list(agent.get("mcp_tools", [])),
                    data_domains=list(agent.get("data_domains", [])),
                )
            )
            uncovered -= coverage

        explanation = (
            f"Resolved {len(required_skills) - len(uncovered)} of "
            f"{len(required_skills)} required skills to {len(selected)} active "
            f"agent(s) using registry capabilities, reliability, and estimated cost."
        )

        return SkillResolution(
            required_skills=list(required_skills),
            selected_agents=selected,
            uncovered_skills=sorted(uncovered),
            selection_explanation=explanation,
        )

    @staticmethod
    def to_dict(result: SkillResolution) -> dict:
        return asdict(result)
