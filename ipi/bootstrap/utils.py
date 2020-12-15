import sys
import typing
from pathlib import Path

from ..pipelines import buildAndInstallWheel
from ..utils.WithInBandBorders import GitHubActionsGroup


def _startswith(a, b) -> bool:
	return a[: len(b)] == b


def unload(name: str):
	name = name.replace("-", "_").split(".")
	for elName in tuple(sys.modules):
		elNameSplitted = elName.split(".")
		if _startswith(elNameSplitted, name):
			del sys.modules[elName]


def bootstrapBySequence(clonedDirs: typing.Mapping[str, Path], bootstrapSequence):
	"""This function installs packages with mutual and self-dependencies
	`clonedDirs` is a mapping that maps names of packages to the dirs (package roots) to which they are cloned. Keys MUST be package names.
	`bootstrapSequence` is a sequence of tuples, each item has the following structure
	(<name of the package>, <dirs of dependencies packages to be added into PYTHONPATH>)
	Instead of dirs of the dependencies one should provide their names (keys in `clonedDirs`), since it is more convenient to look at, and also because this allows elimination of dirs of already installed packages.
	One should not eliminate the installed packages oneself. Just accurately mirror the dependencies."""

	alreadyInstalled = set()
	for name, pythonPaths in bootstrapSequence:
		with GitHubActionsGroup("Installing " + name):
			targetDir = clonedDirs[name]
			pythonPaths = type(pythonPaths)((clonedDirs[el] if isinstance(el, str) else el) for el in pythonPaths if el not in alreadyInstalled)
			buildAndInstallWheel(targetDir, buildPythonPath=(targetDir,) + pythonPaths)
			unload(name)  # to allow reloading from already installed package in order to
		alreadyInstalled |= {name}
