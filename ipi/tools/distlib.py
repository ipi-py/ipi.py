import typing

try:
	from distlib.database import DistributionPath
except ImportError:
	from warnings import warn

	warn("`distlib` is not available, install it")

	import importlib.metadata

	def getInstalledPackageDistribution(name: str):
		try:
			return importlib.metadata.distribution(name)
		except importlib.metadata.PackageNotFoundError:
			return None

else:
	from ..utils import canonicalizePackageNameMulti
	from .pip import SchemeT, getScheme

	def genDistlibPath(scheme: typing.Optional[SchemeT] = None) -> typing.Iterable[str]:
		if scheme is None:
			scheme = getScheme()

		return tuple(scheme[k] for k in ("platlib", "platstdlib", "purelib"))

	def genDistlibDistributionPath(scheme: typing.Optional[SchemeT] = None):
		return DistributionPath(genDistlibPath(scheme))

	def getInstalledPackageDistribution(name: str):
		dp = genDistlibDistributionPath()
		dashName, underscoreName = canonicalizePackageNameMulti(name)

		if dashName != underscoreName:  # it may be any combination!
			dDist = dp.get_distribution(dashName)
			uDist = dp.get_distribution(underscoreName)

			if dDist and uDist:
				raise RuntimeError("Both underscore and dash dists are present, refuse to guess", dDist, uDist)

			return dDist if dDist else uDist
		else:
			return dp.get_distribution(dashName)
