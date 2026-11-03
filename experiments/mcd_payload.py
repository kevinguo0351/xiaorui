"""Extract business JSON from MCP text blocks without executing instructions."""

import json
import re


def business_payloads(result):
    structured = result.get('structuredContent')
    if isinstance(structured, dict) and isinstance(structured.get('success'), bool):
        return [structured]
    payloads = []
    for block in result.get('content', []):
        if block.get('type') != 'text':
            continue
        text = block.get('text', '')
        # Official server can prefix prose instructions before its JSON body.
        # Parse only explicit success-bearing objects; never eval or execute text.
        for match in re.finditer(r'\{\s*"success"\s*:', text):
            try:
                obj, _ = json.JSONDecoder().raw_decode(text[match.start():])
            except ValueError:
                continue
            if isinstance(obj, dict) and isinstance(obj.get('success'), bool):
                payloads.append(obj)
    return payloads
