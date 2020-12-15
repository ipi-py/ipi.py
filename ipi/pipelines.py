"""Single-package build and install pipeline"""

import json
import re
import sys
import typing
from collections import defaultdict
from enum import IntEnum
from functools import partial
from pathlib import Path, PurePath
from tempfile import TemporaryDirectory, mkdtemp

from . import resolver
from .deps import sh
from .deps.icecream import ic
from .deps.packaging import Requirement
from .resolver import InstallationCollection, InstallationTarget, PackageFetcher, ResolutionPrefs, clonePackagesRepos
from .tools import install
from .tools.python import python
from .tools.setup_py import wheelCmd
from .utils import pythonBuild
from .utils.CLICookie import CLICookie
from .utils.metadataExtractor import canonicalizedRequirement, extractMetadata
from .utils.styles import styles
from .utils.WithPythonPath import cookPythonPathEnvDict

standalonePEP517Cmd = python.bake("-m", pythonBuild.__spec__.name)


class PackagesInstaller:
	__slots__ = ("registry",)

	def __init__(self, registry: "IRegistry"):
		self.registry = registry

	def __call__(self, prefs: ResolutionPrefs, names: typing.Collection[str]):
		with PackageFetcher(self.registry) as fetcher:
			toInstallCollections = fetcher(prefs, names)

			for instalaltionCollection in toInstallCollections:
				if instalaltionCollection:  # self.resolved, installDirs[t]
					print(styles.operationName("Installing") + " " + styles.entity(instalaltionCollection.depsKind.packageTypeName) + "s")
					for installationTarget in instalaltionCollection:
						buildAndInstallWheel(installationTarget.installDir)
				else:
					print(styles.success("No " + styles.entity(instalaltionCollection.depsKind.packageTypeName) + "s to install"))


def buildWheelUsingRemotePEP517(packageDir: Path, outDir: Path, pythonPath=()):
	r = pythonBuild.RemotePep517()
	stdinContents = r.serializeArgs(packageDir, outDir)
	res = standalonePEP517Cmd(_in=stdinContents, _env=cookPythonPathEnvDict(pythonPath))
	return r.processOutput(str(res))


def buildWheelUsingSetupPy(packageDir: Path, outDir: Path, pythonPath=()):
	wheelCmd("--dist-dir", outDir, _cwd=packageDir, _env=cookPythonPathEnvDict(pythonPath))

	from .utils.metadataExtractor import extractMetadata

	md = extractMetadata(packageDir)
	print("package name", md.name)

	wheelFiles = list(outDir.glob(md.name + "-*.whl"))
	if len(wheelFiles) > 1:
		raise RuntimeError("More than 1 wheels for given package name in the wheel dir", wheelFiles)

	return wheelFiles[0]


def buildWheel(packageDir: Path, outDir: Path, pythonPath=(), _useSetupPy: bool = False):
	ic(packageDir, outDir, pythonPath, _useSetupPy)
	if not _useSetupPy:
		return pythonBuild.buildWheelUsingPEP517(packageDir, outDir, pythonPath)

	return buildWheelUsingSetupPy(packageDir, outDir, pythonPath)


def buildWheelFromGHUri(wheelsDir: Path, uri: str, buildPythonPath=()):
	suffix = "_" + PurePath(uri).name
	wheel = None
	with TemporaryDirectory(prefix="", dir=Path("."), suffix=suffix) as packageDir:
		packageDir = Path(packageDir).absolute().resolve()
		fetchers[Source.git](uri, packageDir)
		wheel = buildWheel(packageDir, wheelsDir, buildPythonPath)
	return wheel


def buildAndInstallWheel(packageDir: Path, buildPythonPath=(), installPythonPath=(), _useSetupPy: bool = False, installBackend=None, installConfig=None):
	with TemporaryDirectory(prefix="wheels", dir=packageDir) as wheelsDir:
		wheelsDir = Path(wheelsDir).absolute().resolve()
		builtWheel = buildWheel(packageDir, wheelsDir, pythonPath=buildPythonPath, _useSetupPy=_useSetupPy)
		# sudo --preserve-env=PYTHONPATH

		if not installPythonPath:
			if installBackend is None:
				installBackend = install.REINSTALL_BACKEND
		else:
			installBackend = partial(install.pipCliReInstaller, pythonPath=installPythonPath)

		print(installBackend)
		installBackend((builtWheel,), config=installConfig)


def buildAndInstallWheelFromGitURI(uri: str, buildPythonPath=(), installBackend=None, installConfig=None):
	suffix = "_" + PurePath(uri).name
	with TemporaryDirectory(prefix="", dir=Path("."), suffix=suffix) as wheelsDir:
		wheelsDir = Path(wheelsDir).absolute().resolve()
		builtWheel = buildWheelFromGHUri(wheelsDir, uri, buildPythonPath)

		if installBackend is None:
			installBackend = install.REINSTALL_BACKEND

		installBackend((builtWheel,), config=installConfig)
