import typing
from importlib import reload
from pathlib import Path

from ..registries import initRegistries


def getCurrentGitSdistPyprojectToml() -> typing.Optional[Path]:
	rootDir = Path(__file__).resolve().absolute().parent.parent.parent
	gitDir = rootDir / ".git"
	pyprojectToml = rootDir / "pyproject.toml"
	if (gitDir.is_dir() or gitDir.is_file()) and pyprojectToml.is_file():
		return pyprojectToml

	return None


class ItselfBootstrapper:
	__slots__ = ("install", "gipv", "i", "prefs", "regs", "pipelines", "styles")

	def __init__(self):
		self.install = None
		self.gipv = None
		self.pipelines = None

		self.i = None  # type: pipelines.PackagesInstaller
		self.prefs = None  # type: pipelines.ResolutionPrefs
		self.regs = None
		self.styles = None

		self.initInstallTools()
		self.initPipelines()
		self.initStyles()
		self.initRegistries()

	def reloadPip(self):
		from ..tools import pip

		reload(pip)

	def initInstallTools(self):
		from ..tools import install

		self.install = install
		self.gipv = install.getInstalledPackageVersion

	def reloadBuilder(self, pipelines: bool):
		from ..utils import pythonBuild

		reload(pythonBuild)
		if pipelines:
			reloadPipelines()

	def reloadInstaller(self, pipelines: bool):
		self.reloadPip()

		reload(self.install)
		self.initInstallTools()
		if pipelines:
			self.reloadPipelines()

	def initPipelines(self):
		from .. import pipelines

		self.pipelines = pipelines
		self.i = self.pipelines.PackagesInstaller(self.regs)
		self.prefs = self.pipelines.ResolutionPrefs(upgrade=True)

	def reloadPipelines(self):
		"""
		.utils - not used here
		.packaging - used only before this func is needed
		"""

		reload(self.pipelines.resolver)
		reload(self.pipelines)
		self.initPipelines()

	def initStyles(self):
		from ..utils import styles

		self.styles = styles

	def reloadStyles(self, withDependent: bool):
		reload(self.styles)
		self.initStyles()
		if withDependent:
			self.reloadPipelines()

	def initRegistries(self):
		self.regs = initRegistries()

	def reloadUnpin(self, metadataExtractor: bool, pipelines: bool):
		from ..deps import unpin

		reload(unpin)
		if metadataExtractor:
			self.reloadMetadataExtractor(pipelines=pipelines)

	def reloadMetadataExtractor(self, pipelines: bool):
		from ..utils import metadataExtractor

		reload(metadataExtractor)
		if pipelines:
			self.reloadPipelines()

	def reloadPackaging(self, builder: bool, unpin: bool, metadataExtractor: bool, installer: bool, pipelines: bool):
		from ..deps import packaging  # our polyfill for `packaging`

		reload(packaging)
		# pyproject_hooks

		if builder:
			self.reloadBuilder(pipelines=False)
		if unpin:
			self.reloadUnpin(metadataExtractor=False, pipelines=False)
		if metadataExtractor:
			self.reloadMetadataExtractor(pipelines=False)
		if installer:
			self.reloadInstaller(pipelines=False)
		if pipelines:
			self.reloadPipelines()

	def bootstrapPackagingIfNeeded(self):
		from .packaging import getMissingPackagingPackages  # our bootstrapper

		essentialPackagesMissing = getMissingPackagingPackages()
		if essentialPackagesMissing:
			print("Packaging system is not yet bootstrapped. Missing packages: ", essentialPackagesMissing, "Bootstrapping it first...")

			from .packaging import bootstrapPythonPackaging

			bootstrapPythonPackaging()
			self.reloadPackaging(builder=True, unpin=True, metadataExtractor=True, installer=True, pipelines=True)
		else:
			print("Packaging system is already bootstrapped. Installing the rest..")

	def checkIfInstallingFromGitRepoClone(self):
		ppToml = getCurrentGitSdistPyprojectToml()
		if not ppToml:
			raise RuntimeError("`bootstrap.self` must be called from a clone of git repo of ipi")

	def ensureDistlib(self):
		if not self.gipv("distlib"):
			self.i(self.prefs, ["distlib"])
			from ..tools import distlib

			reload(distlib)
			self.reloadInstaller(True)

	def ensureIcecream(self):
		if not self.gipv("icecream"):
			self.i(self.prefs, ["icecream"])
			from ..deps import icecream

			reload(icecream)

			self.reloadPipelines()

	def ensurePeval(self):
		if not self.gipv("peval"):
			self.i(self.prefs, ["peval"])
			from ..deps import peval

			reload(peval)

			self.reloadMetadataExtractor(pipelines=True)

	def ensureInstaller(self):
		if not self.gipv("installer"):
			self.i(self.prefs, ["installer"])
			self.reloadInstaller(True)

	def ensureUninstaller(self):
		if not self.gipv("uninstaller"):
			self.i(self.prefs, ["uninstaller"])
			self.reloadInstaller(True)

	def ensureRequiredDependenciesForCorrectInstallation(self):
		self.ensureDistlib()
		self.ensurePeval()
		self.ensureInstaller()
		self.ensureUninstaller()

	def ensureCLIParsingLib(self):
		if not self.gipv("plumbum"):
			self.i(self.prefs, ["plumbum"])

	def ensureColoringOfOutput(self):
		richConsoleInstalled = self.gipv("RichConsole")

		if not self.gipv("colorama"):
			self.i(self.prefs, ["colorama"])
			if richConsoleInstalled:
				import RichConsole

				reload(RichConsole)
				self.reloadStyles(True)

		if not richConsoleInstalled:
			self.i(self.prefs, ["RichConsole"])
			self.reloadStyles(True)

	def ensureUserInterface(self):
		self.ensureCLIParsingLib()
		self.ensureColoringOfOutput()

	def installItselfUsingBootstrappedDeps(self):
		self.i(self.prefs, ["ipi"])

	def __call__(self):
		self.bootstrapPackagingIfNeeded()
		self.checkIfInstallingFromGitRepoClone()
		self.initRegistries()
		self.initPipelines()

		self.ensureIcecream()
		self.ensureRequiredDependenciesForCorrectInstallation()

		self.ensureUserInterface()

		self.installItselfUsingBootstrappedDeps()


bootstrapItself = ItselfBootstrapper()
