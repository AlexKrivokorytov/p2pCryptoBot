import os
import sys
import webbrowser
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, TypedDict


class FileStat(TypedDict):
    """File coverage statistics."""
    name: str
    coverage: float
    lines: int
    missed: int


class GroupStat(TypedDict):
    """Module group statistics."""
    lines: int
    covered: int
    files: list[FileStat]
    color: str


def get_stats(xml_path: str = "coverage.xml") -> tuple[dict[str, GroupStat], ET.Element] | None:
    """Parse coverage.xml and group data by project modules."""
    if not os.path.exists(xml_path):
        return None

    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Define functional blocks with specific calm colors
    groups_config: dict[str, dict[str, Any]] = {
        "Telegram Handlers": {
            "prefixes": ["bot/handlers/"],
            "color": "#457B9D"  # Muted Blue
        },
        "UI & Keyboards": {
            "prefixes": ["bot/keyboards.py"],
            "color": "#A8DADC"  # Soft Cyan
        },
        "Business Logic": {
            "prefixes": ["services/"],
            "color": "#2A9D8F"  # Muted Teal
        },
        "Blockchain & APIs": {
            "prefixes": ["providers/"],
            "color": "#E9C46A"  # Soft Gold
        },
        "Database Models": {
            "prefixes": ["db/"],
            "color": "#F4A261"  # Soft Orange
        },
        "Background Tasks": {
            "prefixes": ["tasks/"],
            "color": "#E76F51"  # Muted Coral
        },
        "Utilities": {
            "prefixes": ["utils/"],
            "color": "#8D99AE"  # Muted Lavender/Gray
        },
        "Core & Config": {
            "prefixes": [
                "bot/config.py", "bot/main.py",
                "bot/states.py", "bot/middleware.py"
            ],
            "color": "#264653"  # Dark Muted Slate
        }
    }

    stats: dict[str, GroupStat] = {
        name: {
            "lines": 0,
            "covered": 0,
            "files": [],
            "color": str(cfg["color"])
        } for name, cfg in groups_config.items()
    }
    stats["Others"] = {
        "lines": 0,
        "covered": 0,
        "files": [],
        "color": "#64748b"
    }

    for class_node in root.findall(".//class"):
        filename = class_node.get("filename")
        if not filename:
            continue

        line_nodes = class_node.findall("./lines/line")
        lines_valid = len(line_nodes)
        lines_covered = len([ln for ln in line_nodes if ln.get("hits") != "0"])

        if lines_valid == 0:
            continue

        found_group = "Others"
        for name, cfg in groups_config.items():
            prefixes = cfg.get("prefixes", [])
            if isinstance(prefixes, list) and any(filename.startswith(str(p)) for p in prefixes):
                found_group = name
                break

        stats[found_group]["lines"] += lines_valid
        stats[found_group]["covered"] += lines_covered

        coverage = round((lines_covered / lines_valid * 100), 1)

        stats[found_group]["files"].append({
            "name": filename,
            "coverage": coverage,
            "lines": lines_valid,
            "missed": lines_valid - lines_covered,
        })
    return stats, root


def generate_html(stats: dict[str, GroupStat], total_percent: float,
                  output_path: str = "coverage_dashboard.html") -> str:
    """Generate a premium HTML dashboard with donut charts."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>P2P Bot Coverage Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap"
          rel="stylesheet">
    <style>
        body {{
            font-family: 'Inter', sans-serif;
            background-color: #0f172a;
            color: #f8fafc;
            margin: 0;
            padding: 40px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 40px;
            border-bottom: 1px solid #334155;
            padding-bottom: 20px;
        }}
        .header h1 {{
            margin: 0;
            font-size: 2.5rem;
            background: linear-gradient(90deg, #38bdf8, #818cf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .total-badge {{
            background: #1e293b;
            padding: 15px 30px;
            border-radius: 16px;
            border: 1px solid #334155;
            text-align: center;
        }}
        .total-percent {{ font-size: 2rem; font-weight: 700; color: #10b981; }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 30px;
        }}
        .card {{
            background: #1e293b;
            border-radius: 24px;
            padding: 30px;
            border: 1px solid #334155;
            transition: transform 0.2s;
        }}
        .card:hover {{ transform: translateY(-5px); border-color: #38bdf8; }}
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }}
        .card-title {{ font-size: 1.25rem; font-weight: 600; color: #94a3b8; }}
        .chart-container {{
            position: relative;
            height: 200px;
            width: 200px;
            margin: 0 auto 20px;
        }}
        .problems {{
            margin-top: 20px;
            font-size: 0.9rem;
            color: #94a3b8;
            border-top: 1px solid #334155;
            padding-top: 15px;
        }}
        .file-list {{ max-height: 150px; overflow-y: auto; margin-top: 10px; }}
        .file-item {{
            display: flex;
            justify-content: space-between;
            padding: 4px 0;
            border-bottom: 1px solid #1e293b;
        }}
        .low-cov {{ color: #f43f5e; }}
        .footer {{
            margin-top: 60px;
            text-align: center;
            color: #64748b;
            font-size: 0.8rem;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>P2P Bot Coverage Dashboard</h1>
            <p style="color: #64748b; margin-top: 8px;">Generated on {now_str}</p>
        </div>
        <div class="total-badge">
            <div style="font-size: 0.8rem; color: #64748b; text-transform: uppercase;">
                Global Coverage
            </div>
            <div class="total-percent">{total_percent}%</div>
        </div>
    </div>
    <div class="grid">"""

    for name, data in stats.items():
        if data["lines"] == 0:
            continue
        p = round((data["covered"] / data["lines"] * 100), 1)
        c = data["color"]
        problem_files = sorted(
            [f for f in data["files"] if f["coverage"] < 100],
            key=lambda x: x["coverage"]
        )
        safe_name = name.replace(' ', '-').replace('&', 'and')
        chart_id = f"chart-{safe_name}"
        html += f"""
        <div class="card">
            <div class="card-header">
                <span class="card-title">{name}</span>
                <span style="font-weight: 700; color: {c}">{p}%</span>
            </div>
            <div class="chart-container"><canvas id="{chart_id}"></canvas></div>
            <div class="problems">
                <strong>Issues & Warnings:</strong>
                <div class="file-list">"""
        if not problem_files:
            html += '<div style="color: #10b981; margin-top: 5px;">✅ 100% Covered.</div>'
        else:
            for f in problem_files:
                cls = "low-cov" if f["coverage"] < 85 else ""
                fname = f["name"].split("/")[-1]
                line_info = f'{f["coverage"]}% (-{f["missed"]} lines)'
                html += f"""
                <div class="file-item">
                    <span class="{cls}">{fname}</span>
                    <span class="{cls}">{line_info}</span>
                </div>"""
        html += "</div></div></div>"

    html += """
    </div>
    <div class="footer">Premium Testing Infrastructure © 2026 AlexKrivokorytov</div>
    <script>"""
    for name, data in stats.items():
        if data["lines"] == 0:
            continue
        c = data["color"]
        safe_name = name.replace(' ', '-').replace('&', 'and')
        chart_id = f"chart-{safe_name}"
        html += f"""
        new Chart(document.getElementById('{chart_id}'), {{
            type: 'doughnut',
            data: {{
                datasets: [{{
                    data: [{data['covered']}, {data['lines'] - data['covered']}],
                    backgroundColor: ['{c}', '#334155'],
                    borderWidth: 0
                }}]
            }},
            options: {{
                cutout: '80%',
                plugins: {{
                    tooltip: {{ enabled: false }},
                    legend: {{ display: false }}
                }},
                animation: {{ duration: 2000 }}
            }}
        }});"""
    html += "</script></body></html>"
    with open(output_path, "w", encoding="utf-8") as out:
        out.write(html)
    return os.path.realpath(output_path)


def generate_markdown(stats: dict[str, GroupStat], total_percent: float) -> str:
    """Generate a Markdown report with Mermaid pie charts."""
    md = "## 📊 P2P Bot Coverage Dashboard\n\n"
    md += f"> **Global Coverage: {total_percent}%**\n\n"
    md += "| Module | Coverage | Visual State |\n"
    md += "| :--- | :--- | :--- |\n"

    mermaid_blocks = ""
    for name, data in stats.items():
        if data["lines"] == 0:
            continue
        p = round((data["covered"] / data["lines"] * 100), 1)
        status = "✅" if p >= 95 else "⚠️" if p >= 80 else "❌"
        md += f"| {name} | **{p}%** | {status} |\n"

        mermaid_blocks += f"#### {name}\n"
        mermaid_blocks += "```mermaid\n"
        mermaid_blocks += "pie title Coverage\n"
        mermaid_blocks += f'    "Covered" : {data["covered"]}\n'
        mermaid_blocks += f'    "Missed" : {data["lines"] - data["covered"]}\n'
        mermaid_blocks += "```\n\n"

    md += "\n---\n\n### 🔍 Issues & Warnings\n\n"
    for name, data in stats.items():
        problem_files = [f for f in data["files"] if f["coverage"] < 100]
        if problem_files:
            md += f"#### 📁 {name}\n"
            for f in problem_files:
                info = f"**{f['coverage']}%** (missing {f['missed']} lines)"
                md += f"- `{f['name']}`: {info}\n"
            md += "\n"
    md += "\n### 📈 Visual Breakdown\n\n" + mermaid_blocks
    return md


if __name__ == "__main__":
    stats_result = get_stats()
    if not stats_result:
        print("Error: coverage.xml not found.")
        sys.exit(1)
    s, root_xml = stats_result
    total_l = int(root_xml.get("lines-valid", "0"))
    total_c = int(root_xml.get("lines-covered", "0"))
    total_p = round((total_c / total_l * 100), 1) if total_l > 0 else 0.0
    if "--markdown" in sys.argv:
        print(generate_markdown(s, total_p))
    else:
        file_path = generate_html(s, total_p)
        print(f"Dashboard generated: {file_path}")
        webbrowser.open("file://" + file_path)
