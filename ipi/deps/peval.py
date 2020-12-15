import ast
import sys
import typing
from functools import partial
from pathlib import Path

import peval.components
import peval.core.expression

retStmt = ast.Return(
	value=ast.Tuple(
		elts=[
			ast.Name(id="gen_sym", ctx=ast.Load()),
			ast.Name(id="in_env", ctx=ast.Load()),
			ast.List(elts=[], ctx=ast.Load()),
			ast.Dict(keys=[], values=[]),
		],
		ctx=ast.Load(),
	)
)

ifRetStmt = ast.If(
	test=ast.Compare(
		left=ast.Call(
			func=ast.Name(id="len", ctx=ast.Load()),
			args=[ast.Attribute(value=ast.Name(id="statement", ctx=ast.Load()), attr="targets", ctx=ast.Load())],
			keywords=[],
		),
		ops=[ast.NotEq()],
		comparators=[ast.Constant(value=1)],
	),
	body=[retStmt],
	orelse=[],
)


foundF = None


def fixForwardTransfer(foundF):
	branchBody = isCheckIfNodeIsIfSelectingNodeType(foundF.body[0], ("Assign", "AnnAssign")).body
	for el in branchBody:
		if isinstance(el, ast.If):
			r = isCheckIfNodeIsIfSelectingNeededNodeType(("AnnAssign",), el)
			if r:
				el.orelse.append(ifRetStmt)
				print("First stmt patched")
				continue
			r = isCheckIfNodeIsIfSelectingNeededNodeType(("Name",), el)
			if r:
				el1 = isCheckIfNodeIsIfSelectingNodeType(el.orelse[0], ("Name", "Tuple"))
				if el1:
					el1.body.insert(0, retStmt)
					el1.orelse.insert(0, retStmt)
					print("Second & third stmts patched")
					continue
	return foundF


def checkIfIsinstanceCallSelectingNodeTypeAndReturnNodeClasses(c):
	if isinstance(c, ast.Call) and isProperIsinstanceCall(c):
		target, typezToCheck = c.args
		if isinstance(typezToCheck, (ast.Tuple, ast.List)):
			typezToCheck = typezToCheck.elts
		else:
			typezToCheck = (typezToCheck,)

		res = list()
		for el in typezToCheck:
			r = checkIfASTNodeClassAndGetName(el)
			if r:
				res.append(r)
			else:
				return None, None
		return target, tuple(res)
	return None, None


def isProperIsinstanceCall(c):
	cf = c.func
	if isinstance(cf, ast.Name) and cf.id == "isinstance":
		if len(c.args) == 2:
			return True
	return False


def checkIfASTNodeClassAndGetName(n: ast.Attribute):
	if isinstance(n, ast.Attribute):
		v = n.value
		if isinstance(v, ast.Name):
			if v.id == "ast":
				return n.attr
	return None


def selectBranchOnIfElseLadder(ladder: ast.If, extractor):
	currentIf = ladder
	while True:
		if isinstance(currentIf, ast.If):
			extracted = extractor(currentIf)
			if extracted is not None:
				return currentIf
			else:
				assert len(currentIf.orelse) == 1
				currentIf = currentIf.orelse[0]
		else:
			return None


def isCheckIfNodeIsIfSelectingNeededNodeType(targetNodeClasses: typing.Tuple[str], currentIf: ast.If):
	checkedExpr, nodeClasses = checkIfIsinstanceCallSelectingNodeTypeAndReturnNodeClasses(currentIf.test)
	if nodeClasses == targetNodeClasses:
		return nodeClasses


def isCheckIfNodeIsIfSelectingNodeType(ladder: ast.If, targetNodeClasses):
	return selectBranchOnIfElseLadder(ladder, partial(isCheckIfNodeIsIfSelectingNeededNodeType, targetNodeClasses))


def stripAsserts(f):
	newBody = []
	for el in f.body:
		if not isinstance(el, ast.Assert):
			newBody.append(el)
	f.body = newBody
	return f


def patchInternalModuleFunctions(modulePath, funcProcessorsDict: str):
	"""Only internal module functions can be patched this way (the ones imported with `from ... import ...` will not)"""

	module = sys.modules[modulePath]
	pathStr = module.__file__
	if not pathStr:
		raise ValueError("Module has no `__path__`", module)
	path = Path(pathStr)
	moduleAST = ast.parse(path.read_text("utf-8"))

	for el in moduleAST.body:
		if isinstance(el, ast.FunctionDef):
			func = el
			if func.name not in funcProcessorsDict:
				continue

			modifiedFuncAST = funcProcessorsDict[func.name](func)
			globalz = dict(module.__dict__)
			monkeyPatchModule = ast.fix_missing_locations(ast.Module(body=[modifiedFuncAST], type_ignores=[]))
			exec(compile(monkeyPatchModule, "<monkey-patch of " + func.name + ">", "exec"), globalz)
			setattr(module, func.name, globalz[func.name])


def monkeyPatchPeval():
	import peval.components
	import peval.core.expression

	patchInternalModuleFunctions("peval.components.fold", {"forward_transfer": fixForwardTransfer})
	patchInternalModuleFunctions("peval.core.expression", {"peval_call": stripAsserts})
	try:
		del peval.core.expression._peval_expression_dispatcher._handlers[ast.Lambda]
	except KeyError:
		pass


monkeyPatchPeval()

from peval.highlevelapi import _run_components
