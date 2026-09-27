#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AST 掃描：找出「被讀取但從未定義」的模組層／區域名稱（py_compile 抓不到，跑到那一行才會炸）。
用法: python tools/ast_undefined_names.py <檔案...>
"""
import ast, sys, builtins

EXTRA = {"__file__", "__name__", "__doc__", "__package__", "__spec__", "self", "cls"}

def check(path):
    tree = ast.parse(open(path, encoding="utf-8").read(), path)
    defined = set(dir(builtins)) | EXTRA
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                defined.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                a = node.args
                defined.update(x.arg for x in a.args + a.posonlyargs + a.kwonlyargs)
                if a.vararg: defined.add(a.vararg.arg)
                if a.kwarg: defined.add(a.kwarg.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            defined.add(node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)
        elif isinstance(node, (ast.For, ast.AsyncFor)) and isinstance(node.target, ast.Name):
            defined.add(node.target.id)
        elif isinstance(node, ast.comprehension) and isinstance(node.target, ast.Name):
            defined.add(node.target.id)
        elif isinstance(node, ast.Global) or isinstance(node, ast.Nonlocal):
            defined.update(node.names)
    # 同一個模組層名稱被賦值兩次＝很容易「上面的給預設值用、下面的給寫檔用」（2026-09-25 GAIN_CEIL_DB 就中過）
    top = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    top.setdefault(t.id, []).append(node.lineno)
    dup = {k: v for k, v in top.items() if len(v) > 1}
    # 模組層「先用後定義」：PRESETS 用了下面才定義的常數 → import 就炸（同一天中過第二次）
    early = []
    assigned_so_far = set()
    for node in tree.body:
        is_def = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        if not is_def:
            used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
            early += [u for u in sorted(used - assigned_so_far - defined)]
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    assigned_so_far.add(t.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                assigned_so_far.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            assigned_so_far.add(node.name)
        elif isinstance(node, ast.For):
            if isinstance(node.target, ast.Name):
                assigned_so_far.add(node.target.id)
    early = sorted(set(early))
    missing = sorted({n.id for n in ast.walk(tree)
                      if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)} - defined)
    print(f"{path}: {'OK（沒有未定義的名稱）' if not missing else '缺少定義 → ' + ', '.join(missing)}")
    if dup:
        print(f"  ⚠ 模組層重複賦值：{dup}")
    if early:
        print(f"  ⚠ 模組層先用後定義（import 就會炸）：{early}")
    return missing + list(dup) + early

bad = []
for p in sys.argv[1:]:
    bad += check(p)
sys.exit(1 if bad else 0)
