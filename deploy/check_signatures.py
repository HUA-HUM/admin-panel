#!/usr/bin/env python3
"""Verifica que cada llamada self.metodo() del addon respete su firma.

Odoo resuelve los metodos en tiempo de ejecucion, asi que una llamada con un
argumento de mas solo falla cuando el usuario toca el boton. Esto lo detecta
antes de desplegar.
"""
import ast
import glob
import sys


def signatures(tree):
    found = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            args = item.args
            static = any(
                getattr(d, "id", None) == "staticmethod" for d in item.decorator_list
            )
            names = [a.arg for a in args.args][0 if static else 1 :]
            found[item.name] = (
                names,
                len(args.defaults),
                bool(args.vararg),
                bool(args.kwarg),
                [a.arg for a in args.kwonlyargs],
            )
    return found


def check(path):
    tree = ast.parse(open(path).read())
    sigs = signatures(tree)
    problems = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "self"):
            continue
        if func.attr not in sigs:
            continue
        names, ndefaults, star, dstar, kwonly = sigs[func.attr]
        npos = len(node.args)
        kwargs = [k.arg for k in node.keywords if k.arg]
        if not star and npos > len(names):
            problems.append(
                (node.lineno, func.attr, f"{npos} posicionales, acepta {len(names)}")
            )
            continue
        if not dstar:
            unknown = [k for k in kwargs if k not in names and k not in kwonly]
            if unknown:
                problems.append((node.lineno, func.attr, f"kwargs desconocidos: {unknown}"))
                continue
        required = names[: len(names) - ndefaults]
        provided = set(names[:npos]) | set(kwargs)
        missing = [r for r in required if r not in provided]
        if missing and not any(k.arg is None for k in node.keywords):
            problems.append((node.lineno, func.attr, f"faltan: {missing}"))
    return problems


def main():
    total = 0
    for path in sorted(glob.glob("addons/**/*.py", recursive=True)):
        if "__pycache__" in path:
            continue
        for lineno, name, why in check(path):
            print(f"{path}:{lineno}  {name}() -> {why}")
            total += 1
    if total:
        print(f"\n{total} llamada(s) no coinciden con su firma")
        return 1
    print("firmas OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
