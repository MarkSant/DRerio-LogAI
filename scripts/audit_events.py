import ast
import os
from collections import defaultdict
from typing import Any


class EventVisitor(ast.NodeVisitor):
    def __init__(self, filename: str, event_constants: dict[str, str]) -> None:
        self.filename = filename
        self.event_constants = event_constants
        self.publishers: list[dict[str, Any]] = []
        self.subscribers: list[dict[str, Any]] = []

    def resolve_event_name(self, node):
        if isinstance(node, ast.Attribute):
            # Handle Events.NAME
            if isinstance(node.value, ast.Name) and node.value.id == "Events":
                return self.event_constants.get(node.attr, f"Events.{node.attr}")
            # Handle class attributes or other constants
            return f"{node.value.id if isinstance(node.value, ast.Name) else '?'}.{node.attr}"
        elif isinstance(node, ast.Constant):  # python 3.8+
            return node.value
        elif isinstance(node, ast.Str):  # python < 3.8
            return node.s
        return "?"

    def visit_Call(self, node):
        # Check for publish calls
        func_name = ""
        if isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        elif isinstance(node.func, ast.Name):
            func_name = node.func.id

        if func_name in ["publish", "publish_event"]:
            # Assume first arg is event name
            if node.args:
                event_name = self.resolve_event_name(node.args[0])
                payload_keys = []
                # Check for payload in args (positional) or keywords
                # publish(event, payload) or publish(event, data=...)

                # Check 2nd positional arg
                if len(node.args) > 1:
                    payload_node = node.args[1]
                    payload_keys.extend(self.extract_keys(payload_node))

                # Check keywords
                for keyword in node.keywords:
                    if keyword.arg in ["payload", "data"]:
                        payload_keys.extend(self.extract_keys(keyword.value))
                    elif keyword.arg is None:  # **kwargs
                        # It's hard to know keys from **kwargs, but we can note it
                        payload_keys.append("**kwargs")
                    else:
                        # Treat other kwargs as payload items if the signature supports it
                        # (e.g. simple event bus)
                        # But our EventBus takes a dict usually.
                        # Let's stick to explicit payload dicts first.
                        pass

                self.publishers.append(
                    {
                        "event": event_name,
                        "file": self.filename,
                        "line": node.lineno,
                        "payload_keys": payload_keys,
                    }
                )

        # Check for subscribe calls
        if func_name in ["subscribe", "register", "on"]:
            if node.args:
                event_name = self.resolve_event_name(node.args[0])
                self.subscribers.append(
                    {
                        "event": event_name,
                        "file": self.filename,
                        "line": node.lineno,
                        "handler": "unknown",  # Could try to resolve handler name
                    }
                )

        self.generic_visit(node)

    def extract_keys(self, node):
        keys = []
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant):
                    keys.append(key.value)
                elif isinstance(key, ast.Str):
                    keys.append(key.s)
        elif isinstance(node, ast.Call):
            # e.g. dict(a=1, b=2)
            if isinstance(node.func, ast.Name) and node.func.id == "dict":
                for keyword in node.keywords:
                    keys.append(keyword.arg)
        elif isinstance(node, ast.Name):
            keys.append(f"<{node.id}>")
        return keys


def get_event_constants(filepath):
    constants = {}
    with open(filepath) as f:
        tree = ast.parse(f.read())

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Events":
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            # Assume value is constant string
                            if isinstance(item.value, ast.Constant):
                                constants[target.id] = item.value.value
                            elif isinstance(item.value, ast.Str):
                                constants[target.id] = item.value.s
    return constants


def main():
    events_file = "src/zebtrack/ui/events.py"
    event_constants = get_event_constants(events_file)
    # print("Event Constants Loaded:", event_constants)

    all_publishers = []
    all_subscribers = []

    for root, _dirs, files in os.walk("src"):
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                with open(filepath) as f:
                    try:
                        tree = ast.parse(f.read())
                        visitor = EventVisitor(filepath, event_constants)
                        visitor.visit(tree)
                        all_publishers.extend(visitor.publishers)
                        all_subscribers.extend(visitor.subscribers)
                    except Exception as e:
                        print(f"Error parsing {filepath}: {e}")

    # Group by event
    events: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: {"publishers": [], "subscribers": []}
    )

    for pub in all_publishers:
        events[pub["event"]]["publishers"].append(pub)
    for sub in all_subscribers:
        events[sub["event"]]["subscribers"].append(sub)

    # Print Report
    print("# Event Audit Report\n")

    for event_name in sorted(events.keys()):
        if event_name == "?":
            continue

        data = events[event_name]
        print(f"## Event: {event_name}")

        print("  Publishers:")
        if not data["publishers"]:
            print("    - NONE FOUND (Possible Dead Subscriber Code)")
        for p in data["publishers"]:
            keys = ", ".join(map(str, p["payload_keys"]))
            print(f"    - {p['file']}:{p['line']} [Keys: {keys}]")

        print("  Subscribers:")
        if not data["subscribers"]:
            print("    - NONE FOUND (Possible Dead Event)")
        for s in data["subscribers"]:
            print(f"    - {s['file']}:{s['line']}")

        print("")


if __name__ == "__main__":
    main()
