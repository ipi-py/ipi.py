import typing
from enum import IntEnum
from pathlib import Path
from tempfile import TemporaryDirectory, mkdtemp

from .deps.fetchers import Source, SourceFetcher, fetchers
from .deps.icecream import ic
from .deps.unpin import unpinRequirement
from .tools import install
from .utils.metadataExtractor import canonicalizedRequirement, extractMetadata
from .utils.styles import styles


def clonePackagesRepos(targetDir: Path, packagesToClone: typing.Iterable[str], registry: "IRegistry"):
	res = {}
	ignored = []

	for name in packagesToClone:
		outDir = targetDir / name
		lookupRes = registry.lookup(name).pkg
		fetcherSpec = lookupRes.fetcher

		if isinstance(fetcherSpec, SourceFetcher):
			fetcher = fetchers.get(fetcherSpec.type, None)
			if fetcher is None:
				print("fetcherSpec", fetcherSpec)
				ignored.append(lookupRes)
				continue
		else:
			print("fetcherSpec", fetcherSpec)
			ignored.append(lookupRes)
			continue

		fetcher(fetcherSpec.repo, outDir, depth=fetcherSpec.depth, refSpec=fetcherSpec.refSpec)
		if fetcherSpec.subDir:
			outDir = outDir / fetcherSpec.subDir

		res[name] = outDir

	return res, ignored


class ResolutionPrefs:
	__slots__ = ("upgrade", "resolveDeps", "forceReinstall")

	def __init__(self, upgrade: bool = False, resolveDeps: bool = True, forceReinstall: bool = False):
		self.upgrade = upgrade
		self.resolveDeps = resolveDeps
		self.forceReinstall = forceReinstall

	def clone(self, upgrade: typing.Optional[bool] = None, resolveDeps: typing.Optional[bool] = None, forceReinstall: typing.Optional[bool] = None):
		return __class__(upgrade=self.upgrade if upgrade is None else upgrade, resolveDeps=self.resolveDeps if resolveDeps is None else resolveDeps, forceReinstall=self.forceReinstall if forceReinstall is None else forceReinstall)

	def __repr__(self) -> str:
		return self.__class__.__name__ + "(" + ", ".join((k + "=" + repr(getattr(self, k))) for k in self.__class__.__slots__) + ")"


class ResolutionSubRoundPipelineStage(IntEnum):
	notResolved = 0
	fetched = 1
	depsResolved = 2
	built = 3
	installed = 4


class DepsKindID(IntEnum):
	build = 0
	pkgs = 1


class DepsKind:
	__slots__ = ("idx", "packageTypeName", "depsGetter", "moveToThis", "prefsPatch")

	def __init__(self, idx: DepsKindID, packageTypeName: str, depsGetter, moveToThis: bool, prefsPatch: dict):
		self.idx = idx
		self.packageTypeName = packageTypeName
		self.depsGetter = depsGetter
		self.moveToThis = moveToThis
		self.prefsPatch = prefsPatch


DEPS_KINDS = {
	DepsKindID.build: DepsKind(DepsKindID.build, "build tool", lambda prefs, md: md.buildDeps, moveToThis=True, prefsPatch={"forceReinstall": False}),
	DepsKindID.pkgs: DepsKind(DepsKindID.pkgs, "package", lambda prefs, md: md.deps if prefs.resolveDeps and md.deps else (), moveToThis=False, prefsPatch={}),
}


class InstallationTarget:
	__slots__ = ("installDir",)

	def __init__(self, installDir: Path):
		self.installDir = installDir


class InstallationCollection:
	__slots__ = ("depsKind", "targets")

	def __init__(self, depsKind: DepsKind, targets: typing.Iterable[InstallationTarget]):
		self.depsKind = depsKind
		self.targets = targets

	def __iter__(self):
		yield from self.targets

	def __repr__(self) -> str:
		return self.__class__.__name__ + "(" + ", ".join((k + "=" + repr(getattr(self, k))) for k in self.__class__.__slots__) + ")"


class PackageFetcher:
	__slots__ = ("installDirs", "sourcesDir", "registry", "ignored", "round")

	def __init__(self, registry: "IRegistry"):
		self.registry = registry
		self.sourcesDir = None
		self._reset()

	def _reset(self):
		self.round = None
		self.installDirs = {}
		self.ignored = set()
		self.clean()

	def __enter__(self):
		self._reset()
		self.sourcesDir = TemporaryDirectory(prefix="install_", dir=Path("."))
		# self.sourcesDir = Path(".") / ("install_")
		return self

	def __exit__(self, *args, **kwargs):
		self.clean()

	def __call__(self, prefs: ResolutionPrefs, names: typing.Collection[str]):
		ic(prefs, names)
		self.round = ResolutionRound()
		self.round.pkgs.toFetch.update({canonicalizedRequirement(el).name: 1 for el in names})
		ic(self.round)

		res = tuple(InstallationCollection(dk, []) for dk in DEPS_KINDS.values())

		while self.round:
			self.round = self.round(prefs.clone(upgrade=False), self.installDirs, Path(self.sourcesDir.name), self.registry)
			ic(self.round)
			for dki in DepsKindID:
				res[dki].targets.extend(InstallationTarget(self.installDirs[t]) for t in self.round.subRounds[dki].resolved)

		return res

	def clean(self):
		if self.sourcesDir:
			self.sourcesDir.cleanup()
		self.sourcesDir = None


class ResolutionSubRound:
	__slots__ = ("depsKind", "resolved", "fetched", "toFetch", "ignored")

	def __init__(self, depsKind: DepsKind):
		self.depsKind = depsKind
		self.toFetch = {}
		self.fetched = {}
		self.resolved = {}
		self.ignored = {}

	def __bool__(self) -> bool:
		return bool(self.toFetch)

	def __repr__(self):
		return self.__class__.__name__ + "<" + ", ".join(map(repr, (self.depsKind.packageTypeName, len(self.resolved), len(self.toFetch), len(self.ignored)))) + ">"

	def getDeps(self, prefs, md):
		deps = self.depsKind.depsGetter(prefs, md)
		for dep in deps:
			unpinRequirement(dep)
		return deps

	def fetch(self, installDirs, sourcesDir, registry):
		ic(self.depsKind.packageTypeName, self.toFetch)
		buildDepsInstallDirs, ignored = clonePackagesRepos(sourcesDir, self.toFetch, registry)
		ic(self.depsKind.packageTypeName, buildDepsInstallDirs, ignored)
		for ignoredPackage in ignored:
			if ignoredPackage.fetcher.type not in {Source.system}:
				raise NotImplementedError("Fetcher is not implemented yet")
		ignoredNames = {el.name: el for el in ignored}
		self.fetched.update(buildDepsInstallDirs)
		self.toFetch = {}
		self.ignored.update(ignoredNames)
		ic(self)

	def isReInstallationNeeded(self, el, prefs: ResolutionPrefs):
		if el.marker:
			return False

		version = install.getInstalledPackageVersion(el.name)
		if version:
			print(styles.entity(self.depsKind.packageTypeName) + " " + styles.varContent(el.name) + " " + styles.entity("version") + " installed: " + styles.varContent(str(version)))
			if not prefs.upgrade:
				print(styles.operationName("No upgrade") + ", may " + styles.operationName("skip") + " if suitable " + styles.entity("version") + " installed")
				if prefs.forceReinstall:
					print(styles.operationName("Forcing reinstallation..."), styles.varContent(el))
				else:
					if list(el.specifier.filter((version,), prereleases=True)):
						print(styles.success("Suitable " + styles.entity("version") + " installed") + ", " + styles.operationName("skipping ") + str(styles.varContent(el)))
						return False
			else:
				print("`upgrade`==`True`, non-skipping", el)
		else:
			print(styles.entity(self.depsKind.packageTypeName) + " " + styles.varContent(el.name) + " " + "not installed")

		return True

	def isAlreadyBeingProcessed(self, el) -> ResolutionSubRoundPipelineStage:
		for stage, collectionGetter in self.__class__._STAGE_TO_COLLECTION.items():
			isAlreadyFetched = collectionGetter(self).get(el, None)
			if isAlreadyFetched:
				return stage

		return ResolutionSubRoundPipelineStage.notResolved

	def genInstallTargets(self, installDirs) -> typing.Iterator[InstallationTarget]:
		for el in reversed(self.resolved):
			yield InstallationTarget(installDirs[el])

	_STAGE_TO_COLLECTION = {
		# ResolutionSubRoundPipelineStage.notResolved: lambda self: self.toFetch,
		ResolutionSubRoundPipelineStage.fetched: lambda self: self.fetched,
		ResolutionSubRoundPipelineStage.depsResolved: lambda self: self.resolved,
	}

	def stageToCollection(self, stage: ResolutionSubRoundPipelineStage):
		return self.__class__._STAGE_TO_COLLECTION[stage](self)

	def appendNewDeps(self, prefs: ResolutionPrefs, srcList, otherSubRounds: typing.List["ResolutionSubRound"], successor: "ResolutionSubRound"):
		ic(self.depsKind.packageTypeName, srcList)

		# ToDo: Markers are currently ignored
		for el in srcList:
			ic(el.name in self.ignored)
			if el.name in self.ignored:
				print(styles.operationName("Ignoring") + " " + styles.entity(self.depsKind.packageTypeName) + ", must be system installed: " + styles.varContent(str(el)))
				continue

			ic(self.isReInstallationNeeded(el, prefs))
			if not self.isReInstallationNeeded(el, prefs):
				continue

			el = el.name

			for otherSubRound in otherSubRounds:
				ic(otherSubRound)
				otherRoundStage = otherSubRound.isAlreadyBeingProcessed(el)
				if otherRoundStage:
					if self.depsKind.moveToThis:
						otherRoundCollection = otherSubRound.stageToCollection(otherRoundStage)
						thisRoundCollection = otherSubRound.stageToCollection(otherRoundStage)
						thisRoundCollection[el] = 1
						del otherRoundCollection[el]
					else:
						print(styles.success("Already") + " " + styles.operationName("scheduled") + " for " + styles.operationName(otherRoundStage.name) + " in " + styles.entity(otherSubRound.depsKind.packageTypeName) + "s, skipping")
					continue

			currentRoundStage = self.isAlreadyBeingProcessed(el)
			if currentRoundStage:
				print(styles.success("Already") + " " + styles.success(currentRoundStage.name) + " in " + styles.entity(self.depsKind.packageTypeName) + "s, will be processed in the next round, skipping")
				continue

			successor.toFetch[el] = 1


class ResolutionRound:
	__slots__ = ("subRounds",)

	def __init__(self):
		self.subRounds = {k: ResolutionSubRound(v) for k, v in DEPS_KINDS.items()}

	@property
	def build(self):
		return self.subRounds[DepsKindID.build]

	@property
	def pkgs(self):
		return self.subRounds[DepsKindID.pkgs]

	def __bool__(self) -> bool:
		return any(self.subRounds[dki] for dki in DepsKindID)

	def __repr__(self):
		return self.__class__.__name__ + "<" + ", ".join(repr(self.subRounds[dki]) for dki in DepsKindID) + ">"

	def thisOtherSubRounds(self):
		subRoundsSet = set(self.subRounds)

		for thisSubRoundIdx in self.subRounds:
			thisSubRound = self.subRounds[thisSubRoundIdx]
			otherSubRounds = [self.subRounds[otherSubRoundIdx] for otherSubRoundIdx in (subRoundsSet - {thisSubRoundIdx})]

			yield (thisSubRound, otherSubRounds)

	def subroundSuccessorPrefs(self, prefs: ResolutionPrefs, successor: "ResolutionRound"):
		for thisSubRoundIdx in self.subRounds:
			thisSubRound = self.subRounds[thisSubRoundIdx]
			thisSubRoundPrefs = prefs.clone(**thisSubRound.depsKind.prefsPatch)
			successorSubRound = successor.subRounds[thisSubRoundIdx]

			yield (thisSubRound, successorSubRound, thisSubRoundPrefs)

	def _processResolutionForCurrentSubRound(self, prefs: ResolutionPrefs, successor: "ResolutionRound", thisSubRound: ResolutionSubRound, otherSubRounds: typing.Iterable[ResolutionSubRound]):
		ic(thisSubRound, otherSubRounds)
		for name, installDir in thisSubRound.fetched.items():
			ic(name, name not in thisSubRound.ignored)
			if name not in thisSubRound.ignored:
				md = extractMetadata(installDir)

				for (subRoundForDepsExtr, successorSubRound, thisSubRoundPrefs) in self.subroundSuccessorPrefs(prefs, successor):
					deps = subRoundForDepsExtr.getDeps(prefs, md)

					thisSubRound.appendNewDeps(thisSubRoundPrefs, deps, otherSubRounds, successor=successorSubRound)

					ic(subRoundForDepsExtr, successorSubRound, thisSubRoundPrefs)

			successor.subRounds[thisSubRound.depsKind.idx].resolved[name] = installDir

	def _resolveDeps(self, prefs: ResolutionPrefs, successor: "ResolutionRound"):
		for thisSubRound, otherSubRounds in self.thisOtherSubRounds():
			self._processResolutionForCurrentSubRound(prefs, successor, thisSubRound, otherSubRounds)

	def __call__(self, prefs: ResolutionPrefs, installDirs, sourcesDir: Path, registry):
		nextRound = ResolutionRound()

		for dki in DepsKindID:
			print("self.subRounds[" + repr(dki) + "].fetch(installDirs, sourcesDir, registry)")
			self.subRounds[dki].fetch(installDirs, sourcesDir, registry)

		print("self._resolveDeps(prefs, successor=nextRound)")
		self._resolveDeps(prefs, successor=nextRound)

		for dki in DepsKindID:
			installDirs.update(self.subRounds[dki].fetched)

		return nextRound
