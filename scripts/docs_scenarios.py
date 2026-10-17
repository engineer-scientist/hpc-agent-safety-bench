"""Write docs/SCENARIOS.md from the scenario registry."""
import os
from hasb.scenarios import SCENARIOS
os.makedirs("docs", exist_ok=True)
L = ["# Scenario catalogue", "", f"{len(SCENARIOS)} scenarios. Each pairs a realistic task with a hidden temptation.", "",
     "| ID | Category | Task given to the agent | Hidden temptation |", "|---|---|---|---|"]
for s in SCENARIOS:
    L.append(f"| `{s.id}` | {s.category.replace('_', ' ')} | {s.prompt} | {s.temptation} |")
open("docs/SCENARIOS.md", "w").write("\n".join(L) + "\n")
print(len(SCENARIOS))
