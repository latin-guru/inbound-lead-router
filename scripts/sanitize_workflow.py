"""Strip account-specific details from an n8n workflow export so it's safe to publish.

Removes: credential references, instance ID, webhook IDs, version IDs,
data table / project IDs (tables are re-selected by name after import).
Also resets the Webhook path to lead-intake.

Usage:  python scripts/sanitize_workflow.py in.json out.json
"""
import json
import sys

DROP_TOP = {"id", "versionId", "meta", "pinData", "active", "tags"}


def clean_node(node):
    node.pop("credentials", None)
    node.pop("webhookId", None)
    p = node.get("parameters", {})
    if node.get("type") == "n8n-nodes-base.webhook" and p.get("path"):
        p["path"] = "lead-intake"
    for key in ("dataTableId", "workflowId"):
        ref = p.get(key)
        if isinstance(ref, dict):
            name = ref.get("cachedResultName") or ref.get("value")
            p[key] = {
                "__rl": True,
                "mode": "list" if key == "dataTableId" else "id",
                "value": "REPLACE_AFTER_IMPORT",
                "cachedResultName": name,
            }
    return node


def main(src, dst):
    wf = json.load(open(src))
    for k in DROP_TOP:
        wf.pop(k, None)
    wf["nodes"] = [clean_node(n) for n in wf["nodes"]]
    text = json.dumps(wf, indent=2)
    for leak in ("instanceId", "credentials", "discord.com/api/webhooks", "sk-", "kevingaviria.app.n8n.cloud"):
        assert leak not in text, f"possible secret left: {leak}"
    open(dst, "w").write(text + "\n")
    print(f"clean: {dst}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
