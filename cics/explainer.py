"""
Evidence-bounded AI explainer (RQ3).
Passes only structured finding evidence to the LLM – prevents hallucination.
"""

import json
import os


def explain_finding(finding_dict: dict, client=None) -> str:
    """
    Generate a natural-language explanation for a CICS finding.

    Uses the Anthropic SDK (claude-sonnet-4-6).
    Set ANTHROPIC_API_KEY in environment before calling.

    Parameters
    ----------
    finding_dict : dict  – serialised Finding (from Finding.to_dict())
    client       : anthropic.Anthropic | None  – reuse an existing client

    Returns
    -------
    str – 4-7 line explanation with 1-2 mitigation suggestions.
    """
    try:
        import anthropic
    except ImportError:
        return "[anthropic package not installed – skipping explanation]"

    if client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return "[ANTHROPIC_API_KEY not set – skipping explanation]"
        client = anthropic.Anthropic(api_key=api_key)

    evidence_block = json.dumps(finding_dict["evidence"], indent=2)
    prompt = f"""You are a FinOps advisor reviewing a Terraform infrastructure change.
A rule-based analysis has detected the following cost-impact signal.
You MUST only use the evidence provided below – do not add assumptions or pricing details.

Rule triggered : {finding_dict["rule_id"]}
Category       : {finding_dict["category"]}
Direction      : {finding_dict["direction"]}
Severity       : {finding_dict["severity"]}
Resource       : {finding_dict["resource_type"]} at {finding_dict["resource_address"]}
Actions        : {finding_dict["actions"]}
Evidence       :
{evidence_block}

Write a 4-7 line explanation that:
1. States what changed and why it is a cost driver (cite the evidence fields by name).
2. Gives 1-2 concrete mitigation suggestions the reviewer can act on.
3. Does NOT estimate exact dollar amounts.
4. Ends with: "Evidence trace: <list the evidence key=value pairs used>".

Keep the tone concise and reviewer-friendly."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def explain_findings_bulk(findings: list, save_path=None) -> list:
    """
    Explain a list of findings, optionally saving results to a JSON file.
    Returns findings list with 'explanation' field populated.
    """
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    except Exception:
        client = None

    results = []
    for f in findings:
        fd = f.to_dict() if hasattr(f, "to_dict") else f
        fd["explanation"] = explain_finding(fd, client=client)
        results.append(fd)

    if save_path:
        import pathlib
        pathlib.Path(save_path).write_text(
            json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return results
