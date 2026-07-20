import json
from datetime import datetime

projects = [
    {
        "project": "Automatic Test Project",
        "county": "Boone",
        "status": "Bidding",
        "value": "$20M",
        "opportunity": "High",
        "last_updated": datetime.now().strftime("%Y-%m-%d")
    },
    {
        "project": "Cincinnati Test Development",
        "county": "Hamilton",
        "status": "Planning",
        "value": "$12M",
        "opportunity": "Medium",
        "last_updated": datetime.now().strftime("%Y-%m-%d")
    }
]

with open("projects.json", "w", encoding="utf-8") as file:
    json.dump(projects, file, indent=2)

print(f"Updated projects.json with {len(projects)} projects.")
