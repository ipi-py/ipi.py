try:
	from packaging.requirements import Requirement
	from packaging.specifiers import Specifier, SpecifierSet
	from packaging.version import Version
except ImportError:
	_polyfillMarker = "Polyfill"

	class Version:
		__slots__ = ()

	Version.__name__ += _polyfillMarker

	class Specifier(str):
		__slots__ = ()

	Specifier.__name__ += _polyfillMarker

	class SpecifierSet(str):
		__slots__ = ()

	SpecifierSet.__name__ += _polyfillMarker

	class Requirement:
		__slots__ = ("name", "specifier", "marker")

		def __init__(self, name):
			nameSplitted = name.split(" ")
			self.name = nameSplitted[0]
			self.specifier = None
			self.marker = None

	Requirement.__name__ += _polyfillMarker
