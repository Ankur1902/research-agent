import html
import io

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def markdown(report: dict) -> str:
    text = f"# {report['title']}\n\n{report['summary']}\n\n"
    findings = report.get("findings", [])
    for section in report["sections"]:
        text += f"## {section['title']}\n\n"
        for index in section["finding_indices"]:
            finding = findings[index]
            text += (
                f"**{finding['kind']} · {finding['status']}** {finding['text']} "
                + " ".join(f"[{key}]" for key in finding["citations"])
                + "\n\n"
            )
    text += "## Limitations\n\n" + "\n".join(f"- {item}" for item in report["limitations"])
    text += "\n\n## Sources\n\n" + "\n".join(
        f"[{s['citation']}] {s['title']} — {s['url']}" for s in report.get("sources", [])
    )
    return text


def export_pdf(report: dict) -> bytes:
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    elements = []
    for line in markdown(report).splitlines():
        if line.strip():
            style = (
                styles["Title"]
                if line.startswith("# ")
                else styles["Heading2"]
                if line.startswith("## ")
                else styles["BodyText"]
            )
            elements.extend([Paragraph(html.escape(line.lstrip("# ")), style), Spacer(1, 8)])
    SimpleDocTemplate(buffer).build(elements)
    return buffer.getvalue()
