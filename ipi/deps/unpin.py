try:
	from unpin.patcher import TransformsConfig, filterSpecifiers
except:
	from warnings import warn

	warn("install `unpin` in order remove only malicious pinnings")

	from .packaging import SpecifierSet

	def unpinRequirement(req: "packaging.requirements.Requirement") -> None:
		req.specifier = SpecifierSet("")

else:
	tcfg = TransformsConfig()

	def unpinRequirement(req: "packaging.requirements.Requirement") -> None:
		filterSpecifiers(req.specifier, tcfg)
