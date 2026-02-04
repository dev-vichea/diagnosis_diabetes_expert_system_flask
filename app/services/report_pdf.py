from datetime import datetime
from html import escape
from io import BytesIO
from typing import Any, Dict, Iterable, List, Optional

from app.models import Assessment


def _fmt_text(value: Any, default: str = "-") -> str:
    if value is None:
        return default
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _fmt_date(value: Any) -> str:
    if not value:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%B %d, %Y %H:%M UTC")
    return str(value)


def _fmt_short_datetime(value: Optional[datetime]) -> str:
    if not value:
        return "-"
    return value.strftime("%Y-%m-%d, %H:%M")


def _safe_paragraph(text: str, style: Any, paragraph_cls: Any) -> Any:
    safe_text = escape(text or "-").replace("\n", "<br/>")
    return paragraph_cls(safe_text, style)

def _bullet_rows(items: Iterable[str], style: Any, paragraph_cls: Any) -> List[Any]:
    items = [item for item in items if item]
    if not items:
        return [_safe_paragraph("None reported.", style, paragraph_cls)]
    rows = []
    for item in items:
        rows.append(paragraph_cls(escape(str(item)), style, bulletText="•"))
    return rows


def _symptom_label(symptom: Any) -> str:
    if not symptom:
        return "-"
    return symptom.name or symptom.code or symptom.question_text or "-"


def _kv_lines(pairs: Iterable[tuple[str, Any]], style: Any, paragraph_cls: Any) -> List[Any]:
    lines = []
    for label, value in pairs:
        safe_label = escape(str(label))
        safe_value = escape(_fmt_text(value))
        lines.append(paragraph_cls(f"<b>{safe_label}:</b> {safe_value}", style))
    return lines


def _boxed_section(
    title: str,
    subtitle: Optional[str],
    content: List[Any],
    paragraph_cls: Any,
    table_cls: Any,
    table_style_cls: Any,
    colors_module: Any,
    width: float,
    title_style: Any,
    subtitle_style: Any,
) -> Any:
    header_items = [paragraph_cls(f"<b>{escape(title)}</b>", title_style)]
    if subtitle:
        header_items.append(paragraph_cls(escape(subtitle), subtitle_style))
    rows = header_items + content
    section_table = table_cls([[row] for row in rows], colWidths=[width], splitByRow=1)
    section_table.setStyle(
        table_style_cls(
            [
                ("BOX", (0, 0), (-1, -1), 0.8, colors_module.HexColor("#cbd5e1")),
                ("ROUNDEDCORNERS", [6, 6, 6, 6]),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("TOPPADDING", (0, 1), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return section_table


def build_report_pdf(assessment: Assessment, report: Dict[str, Any]) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError("ReportLab is required for PDF export. Install with `pip install reportlab`.") from exc

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
        title="Assessment Report",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=18,
        textColor="#0f1f3d",
        spaceAfter=6,
    )
    date_style = ParagraphStyle(
        "ReportDate",
        parent=styles["BodyText"],
        fontSize=9,
        textColor="#334155",
        spaceAfter=12,
    )
    section_heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading3"],
        fontSize=11,
        textColor="#1e3a8a",
        spaceAfter=6,
    )
    subheading_style = ParagraphStyle(
        "SectionSubHeading",
        parent=styles["Heading3"],
        fontSize=9,
        spaceBefore=6,
        spaceAfter=3,
        textColor="#1f2937",
    )
    body_style = styles["BodyText"]
    body_style.fontSize = 9
    body_style.leading = 12
    body_style.spaceAfter = 2
    section_title_style = ParagraphStyle(
        "SectionTitle",
        parent=styles["Heading3"],
        fontSize=9.5,
        textColor="#1f2937",
        spaceAfter=2,
    )
    section_subtitle_style = ParagraphStyle(
        "SectionSubtitle",
        parent=styles["BodyText"],
        fontSize=8.5,
        textColor="#64748b",
        spaceAfter=4,
    )

    patient_name = "-"
    patient_email = "-"
    if assessment.user:
        patient_name = assessment.user.name or "-"
        patient_email = assessment.user.email or "-"

    elements: List[Any] = []
    elements.append(Paragraph("Symptom Assessment Report", title_style))
    report_date = assessment.completed_at or assessment.started_at or datetime.utcnow()
    elements.append(Paragraph(_fmt_short_datetime(report_date), date_style))
    elements.append(Spacer(1, 2))

    summary_content = _kv_lines(
        [
            ("Assessment ID", assessment.id),
            ("Patient", patient_name),
            ("Email", patient_email),
            ("Status", assessment.status),
            ("Started", _fmt_date(assessment.started_at)),
            ("Completed", _fmt_date(assessment.completed_at)),
        ],
        body_style,
        Paragraph,
    )
    elements.append(Paragraph("Patient", section_heading_style))
    elements.append(_boxed_section(
        "Patient details",
        "Basic information for this assessment.",
        summary_content,
        Paragraph,
        Table,
        TableStyle,
        colors,
        doc.width,
        section_title_style,
        section_subtitle_style,
    ))
    elements.append(Spacer(1, 6))

    if report.get("status") == "IN_PROGRESS":
        pending_content = [_safe_paragraph("Assessment is still in progress.", body_style, Paragraph)]
        elements.append(_boxed_section(
            "Assessment Summary",
            "Assessment status.",
            pending_content,
            Paragraph,
            Table,
            TableStyle,
            colors,
            doc.width,
            section_title_style,
            section_subtitle_style,
        ))
        doc.build(elements)
        return buffer.getvalue()

    risk = report.get("risk_assessment") or {}
    risk_content = _kv_lines(
        [
            ("Diagnosis", risk.get("diagnosis_name")),
            ("Diagnosis Code", risk.get("diagnosis_code")),
            ("Risk Level", risk.get("risk_level")),
            ("Confidence", risk.get("confidence")),
        ],
        body_style,
        Paragraph,
    )
    elements.append(Paragraph("Medical History", section_heading_style))
    elements.append(_boxed_section(
        "Risk assessment",
        "Summary of the predicted risk and confidence.",
        risk_content,
        Paragraph,
        Table,
        TableStyle,
        colors,
        doc.width,
        section_title_style,
        section_subtitle_style,
    ))
    elements.append(Spacer(1, 6))

    yes_list: List[str] = []
    no_list: List[str] = []
    for fact in assessment.facts or []:
        symptom = getattr(fact, "symptom", None)
        if not symptom or symptom.input_type != "BOOLEAN":
            continue
        if fact.value_bool is True:
            yes_list.append(_symptom_label(symptom))
        elif fact.value_bool is False:
            no_list.append(_symptom_label(symptom))
    symptom_content: List[Any] = [
        Paragraph("Reported", subheading_style),
        *_bullet_rows(yes_list, body_style, Paragraph),
        Paragraph("Not Reported", subheading_style),
        *_bullet_rows(no_list, body_style, Paragraph),
    ]
    elements.append(Paragraph("Symptoms", section_heading_style))
    elements.append(_boxed_section(
        "Symptoms",
        "Symptoms marked during the assessment.",
        symptom_content,
        Paragraph,
        Table,
        TableStyle,
        colors,
        doc.width,
        section_title_style,
        section_subtitle_style,
    ))
    elements.append(Spacer(1, 6))

    reasoning = report.get("reasoning") or []
    if reasoning:
        elements.append(Paragraph("Reasoning", section_heading_style))
        elements.append(_boxed_section(
            "Reasoning",
            "Rule explanations tied to the diagnosis.",
            _bullet_rows(reasoning, body_style, Paragraph),
            Paragraph,
            Table,
            TableStyle,
            colors,
            doc.width,
            section_title_style,
            section_subtitle_style,
        ))
        elements.append(Spacer(1, 8))

    advice = report.get("advice") or {}
    advice_content = advice.get("content") or ""
    if advice_content:
        elements.append(Paragraph("Advice", section_heading_style))
        elements.append(_boxed_section(
            "Advice",
            "Guidance based on the assessment outcome.",
            [_safe_paragraph(advice_content, body_style, Paragraph)],
            Paragraph,
            Table,
            TableStyle,
            colors,
            doc.width,
            section_title_style,
            section_subtitle_style,
        ))
        elements.append(Spacer(1, 8))

    recommendations = (advice.get("recommendations") or {}) if advice else {}
    screening_tests = recommendations.get("screening_tests") or []
    if screening_tests:
        elements.append(Paragraph("Recommendations", section_heading_style))
        elements.append(_boxed_section(
            "Recommended Screening",
            "Follow-up tests to consider.",
            _bullet_rows(screening_tests, body_style, Paragraph),
            Paragraph,
            Table,
            TableStyle,
            colors,
            doc.width,
            section_title_style,
            section_subtitle_style,
        ))
        elements.append(Spacer(1, 8))

    candidates = report.get("top_candidates") or []
    if candidates:
        elements.append(Paragraph("Top Candidates", section_heading_style))
        cand_lines = []
        for cand in candidates:
            line = (
                f"{_fmt_text(cand.get('diagnosis_code'))} — "
                f"Risk: {_fmt_text(cand.get('risk_level'))} · "
                f"Confidence: {_fmt_text(cand.get('est_confidence'))} · "
                f"Score: {_fmt_text(cand.get('score'))}"
            )
            cand_lines.append(line)
        elements.append(_boxed_section(
            "Top Candidates",
            "Other likely diagnoses considered.",
            _bullet_rows(cand_lines, body_style, Paragraph),
            Paragraph,
            Table,
            TableStyle,
            colors,
            doc.width,
            section_title_style,
            section_subtitle_style,
        ))
        elements.append(Spacer(1, 8))

    next_questions = report.get("next_best_questions") or []
    if next_questions:
        elements.append(Paragraph("Next Best Questions", section_heading_style))
        question_lines = []
        for item in next_questions:
            code = item.get("code") or ""
            text = item.get("text") or ""
            question_lines.append(f"{code} - {text}".strip(" -"))
        elements.append(_boxed_section(
            "Next Best Questions",
            "Follow-up questions for increased accuracy.",
            _bullet_rows(question_lines, body_style, Paragraph),
            Paragraph,
            Table,
            TableStyle,
            colors,
            doc.width,
            section_title_style,
            section_subtitle_style,
        ))
        elements.append(Spacer(1, 8))

    elements.append(Spacer(1, 2))
    elements.append(
        _safe_paragraph(
            "This report is for informational purposes only and does not replace medical advice.",
            body_style,
            Paragraph,
        )
    )

    doc.build(elements)
    return buffer.getvalue()
