#!/usr/bin/env python3
"""
ModuleFlow — Static analysis of Python project structure.
Scans all .py files, extracts imports/functions/calls, outputs JSON graph.
"""

import ast
import os
import json
import sys
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).resolve().parent.parent
SKIP_DIRS = {
    "__pycache__", ".git", ".venv", "venv", "env", "node_modules",
    ".opencode", "static", "storage", "logs", "codeflow", "moduleflow",
    "unique", "doc", "busi_doc", "langgraph_example",
}
SKIP_FILES = {"activate.sh"}


def should_skip(path: Path) -> bool:
    parts = path.relative_to(BASE_DIR).parts
    if any(p in SKIP_DIRS for p in parts):
        return True
    if path.name in SKIP_FILES:
        return True
    # Skip hidden files (like .py, .py_1)
    if path.name.startswith(".") and not path.name.startswith("__"):
        return True
    return False


def extract_imports(tree: ast.AST) -> list[dict]:
    """Extract all import statements."""
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append({
                    "module": alias.name,
                    "name": alias.asname or alias.name,
                    "kind": "import",
                })
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imports.append({
                    "module": module,
                    "name": alias.name,
                    "kind": "from_import",
                    "level": node.level,
                })
    return imports


def extract_definitions(tree: ast.AST) -> dict:
    """Extract function and class definitions."""
    funcs = []
    classes = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            args = [a.arg for a in node.args.args if a.arg != "self" and a.arg != "cls"]
            funcs.append({
                "name": node.name,
                "line": node.lineno,
                "args": args,
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "decorators": [_deco_name(d) for d in node.decorator_list],
            })
        elif isinstance(node, ast.ClassDef):
            methods = []
            for item in ast.iter_child_nodes(node):
                if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                    m_args = [a.arg for a in item.args.args if a.arg not in ("self", "cls")]
                    methods.append({
                        "name": item.name,
                        "line": item.lineno,
                        "args": m_args,
                        "is_async": isinstance(item, ast.AsyncFunctionDef),
                    })
            bases = []
            for base in node.bases:
                if isinstance(base, ast.Name):
                    bases.append(base.id)
                elif isinstance(base, ast.Attribute):
                    bases.append(ast.unparse(base))
            classes.append({
                "name": node.name,
                "line": node.lineno,
                "bases": bases,
                "methods": methods,
            })
    return {"functions": funcs, "classes": classes}


def _deco_name(node) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return ast.unparse(node)
    if isinstance(node, ast.Call):
        return _deco_name(node.func)
    return "?"


def extract_calls(tree: ast.AST) -> list[str]:
    """Extract all function/method calls in the file."""
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name:
                calls.append(name)
    return calls


def _call_name(func_node) -> str | None:
    if isinstance(func_node, ast.Name):
        return func_node.id
    if isinstance(func_node, ast.Attribute):
        parts = []
        current = func_node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def extract_external_refs(tree: ast.AST) -> list[str]:
    """Extract references to names that look like local imports."""
    refs = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            refs.add(node.id)
        elif isinstance(node, ast.Attribute):
            # Walk the chain to get root name
            current = node
            while isinstance(current, ast.Attribute):
                current = current.value
            if isinstance(current, ast.Name):
                refs.add(current.id)
    return list(refs)


def analyze_file(filepath: Path, known_local_modules: set[str] | None = None) -> dict:
    """Parse a single Python file."""
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError) as e:
        return {"error": str(e)}

    imports = extract_imports(tree)
    defs = extract_definitions(tree)
    calls = extract_calls(tree)

    # Local imports (within project)
    local_imports = []
    external_imports = []
    local_modules = known_local_modules or set()

    for imp in imports:
        mod = imp["module"]
        if not mod:
            continue
        top = mod.split(".")[0]
        # Check if top-level module is local
        if top in local_modules or (BASE_DIR / f"{top}.py").exists() or (BASE_DIR / top).is_dir():
            local_imports.append(imp)
        else:
            external_imports.append(imp)

    return {
        "imports": imports,
        "local_imports": local_imports,
        "external_imports": external_imports,
        "functions": defs["functions"],
        "classes": defs["classes"],
        "calls": calls,
        "lines": len(source.splitlines()),
    }


def resolve_import_target(imp: dict, file_path: Path, file_map: dict) -> str | None:
    """Try to resolve an import to a local file."""
    module = imp["module"]
    if not module:
        return None

    parts = module.split(".")
    top = parts[0]

    # Direct file match
    if f"{top}.py" in file_map:
        return f"{top}.py"

    # Package match
    pkg_dir = BASE_DIR / top
    if pkg_dir.is_dir():
        sub = ".".join(parts[1:])
        if sub:
            sub_file = pkg_dir / f"{sub.replace('.', '/')}.py"
            if sub_file.exists():
                return str(sub_file.relative_to(BASE_DIR))
        init_file = pkg_dir / "__init__.py"
        if init_file.exists():
            return str(pkg_dir.relative_to(BASE_DIR)) + "/__init__.py"
        # Just return the package dir
        return str(pkg_dir.relative_to(BASE_DIR)) + "/"

    # Try as submodule of a package
    # e.g. from utils.shared_logic import X -> utils/shared_logic.py
    if len(parts) >= 2:
        candidate = BASE_DIR / (parts[0]) / f"{'_'.join(parts[1:])}.py"
        if candidate.exists():
            return str(candidate.relative_to(BASE_DIR))
        candidate2 = BASE_DIR / f"{parts[0]}_{'_'.join(parts[1:])}.py"
        if candidate2.exists():
            return str(candidate2.relative_to(BASE_DIR))

    return None


def build_graph(project_dir: Path) -> dict:
    """Build the full module flow graph."""
    # Collect all Python files
    py_files = []
    for root, dirs, files in os.walk(project_dir):
        root_path = Path(root)
        # Skip hidden dirs and __pycache__
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]

        for f in files:
            if f.endswith(".py") and f != "activate.sh":
                fp = root_path / f
                if not should_skip(fp):
                    py_files.append(fp)

    # Analyze each file
    file_map = {}
    nodes = []
    edges = []
    all_defined_functions = {}  # "module.func" -> file

    # Build set of known local module names
    known_local = set()
    for fp in py_files:
        rel = str(fp.relative_to(project_dir))
        stem = fp.stem
        known_local.add(stem)
        parts = Path(rel).parts
        if len(parts) > 1:
            known_local.add(parts[0])

    for fp in sorted(py_files):
        rel = str(fp.relative_to(project_dir))
        result = analyze_file(fp, known_local)
        if "error" in result and not result.get("functions"):
            continue

        file_map[rel] = result

        # File node
        nodes.append({
            "id": rel,
            "type": "file",
            "name": fp.stem,
            "path": rel,
            "lines": result.get("lines", 0),
            "imports_count": len(result.get("local_imports", [])),
            "functions_count": len(result.get("functions", [])),
            "classes_count": len(result.get("classes", [])),
        })

        # Function nodes
        for fn in result.get("functions", []):
            fn_id = f"{rel}::{fn['name']}"
            all_defined_functions[fn["name"]] = rel
            nodes.append({
                "id": fn_id,
                "type": "function",
                "name": fn["name"],
                "file": rel,
                "line": fn["line"],
                "args": fn["args"],
                "is_async": fn.get("is_async", False),
            })
            # Edge: file -> function
            edges.append({
                "source": rel,
                "target": fn_id,
                "type": "defines",
            })

        # Class nodes
        for cls in result.get("classes", []):
            cls_id = f"{rel}::{cls['name']}"
            nodes.append({
                "id": cls_id,
                "type": "class",
                "name": cls["name"],
                "file": rel,
                "line": cls["line"],
                "bases": cls["bases"],
                "methods_count": len(cls["methods"]),
            })
            edges.append({
                "source": rel,
                "target": cls_id,
                "type": "defines",
            })

            for method in cls["methods"]:
                method_id = f"{rel}::{cls['name']}.{method['name']}"
                all_defined_functions[method["name"]] = rel
                nodes.append({
                    "id": method_id,
                    "type": "function",
                    "name": method["name"],
                    "file": rel,
                    "line": method["line"],
                    "args": method["args"],
                    "is_async": method.get("is_async", False),
                    "class": cls["name"],
                })
                edges.append({
                    "source": cls_id,
                    "target": method_id,
                    "type": "defines",
                })

        # Import edges
        for imp in result.get("local_imports", []):
            target_file = resolve_import_target(imp, fp, file_map)
            if target_file and target_file in file_map:
                edges.append({
                    "source": rel,
                    "target": target_file,
                    "type": "imports",
                    "module": imp["module"],
                    "name": imp["name"],
                })

        # Call edges — match calls to defined functions
        defined_names = set(all_defined_functions.keys())
        for call_name in result.get("calls", []):
            # Direct function call
            if call_name in defined_names:
                target_file = all_defined_functions[call_name]
                call_file_rel = str(fp.relative_to(project_dir))
                if call_file_rel != target_file:
                    edges.append({
                        "source": call_file_rel,
                        "target": f"{target_file}::{call_name}",
                        "type": "calls",
                    })
            # Method call like module.func
            if "." in call_name:
                parts = call_name.split(".")
                if len(parts) == 2:
                    mod_name, func_name = parts
                    if func_name in defined_names:
                        target_file = all_defined_functions[func_name]
                        call_file_rel = str(fp.relative_to(project_dir))
                        if call_file_rel != target_file:
                            edges.append({
                                "source": call_file_rel,
                                "target": f"{target_file}::{func_name}",
                                "type": "calls",
                            })

    # Compute stats
    file_nodes = [n for n in nodes if n["type"] == "file"]
    func_nodes = [n for n in nodes if n["type"] == "function"]
    class_nodes = [n for n in nodes if n["type"] == "class"]
    import_edges = [e for e in edges if e["type"] == "imports"]
    call_edges = [e for e in edges if e["type"] == "calls"]

    # Most imported files
    import_count = defaultdict(int)
    for e in import_edges:
        import_count[e["target"]] += 1
    top_imported = sorted(import_count.items(), key=lambda x: -x[1])[:10]

    # Most calling files
    call_count = defaultdict(int)
    for e in call_edges:
        call_count[e["source"]] += 1
    top_callers = sorted(call_count.items(), key=lambda x: -x[1])[:10]

    # Most called functions
    called_count = defaultdict(int)
    for e in call_edges:
        called_count[e["target"]] += 1
    top_called = sorted(called_count.items(), key=lambda x: -x[1])[:10]

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "total_files": len(file_nodes),
            "total_functions": len(func_nodes),
            "total_classes": len(class_nodes),
            "total_import_edges": len(import_edges),
            "total_call_edges": len(call_edges),
            "total_lines": sum(n.get("lines", 0) for n in file_nodes),
            "top_imported_files": [{"file": f, "count": c} for f, c in top_imported],
            "top_callers": [{"file": f, "count": c} for f, c in top_callers],
            "top_called_functions": [{"function": f, "count": c} for f, c in top_called],
        },
    }


def main():
    project_dir = BASE_DIR
    print(f"Scanning {project_dir} ...")

    graph = build_graph(project_dir)

    output_json = project_dir / "moduleflow" / "graph.json"
    output_json.write_text(json.dumps(graph, indent=2, default=str))

    # Generate self-contained HTML with embedded data
    html_template = project_dir / "moduleflow" / "index.html"
    output_html = project_dir / "moduleflow" / "flow.html"
    if html_template.exists():
        html = html_template.read_text(encoding="utf-8")
        # Replace the fetch() call with embedded data
        embedded = json.dumps(graph, default=str)
        new_init = f"""
async function init() {{
  try {{
    graphData = {embedded};
  }} catch (e) {{
    document.getElementById('stats').innerHTML = '<div style="color:var(--red);font-size:11px;padding:12px">Error loading data: ' + e.message + '</div>';
    return;
  }}"""
        html = html.replace("async function init() {\n  try {\n    const resp = await fetch('graph.json');\n    graphData = await resp.json();\n  } catch (e) {\n    document.getElementById('stats').innerHTML = '<div style=\"color:var(--red);font-size:11px;padding:12px\">graph.json not found. Run: python moduleflow/analyze.py</div>';\n    return;\n  }", new_init)
        output_html.write_text(html, encoding="utf-8")
        print(f"  HTML:      {output_html}")

    print(f"Done!")
    print(f"  Files:     {graph['stats']['total_files']}")
    print(f"  Functions: {graph['stats']['total_functions']}")
    print(f"  Classes:   {graph['stats']['total_classes']}")
    print(f"  Imports:   {graph['stats']['total_import_edges']}")
    print(f"  Calls:     {graph['stats']['total_call_edges']}")
    print(f"  Lines:     {graph['stats']['total_lines']}")
    print(f"  Output:    {output_json}")


if __name__ == "__main__":
    main()
