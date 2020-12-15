import typing
from enum import IntEnum
from pathlib import PurePosixPath
from urllib.parse import ParseResult, unquote_plus, urljoin, urlparse, urlunparse

URIDetectorInternalUriReprT = typing.Any


class URIType(IntEnum):
	unknown = 0
	root = 1
	file = 2
	bug = 3
	wiki = 4
	page = 5
	release = 6


class URIDetector:
	NAME = None  # type: str

	@classmethod
	def detect(cls, uri: ParseResult) -> typing.Optional[URIDetectorInternalUriReprT]:
		raise NotImplementedError


class GitHubURIDetector(URIDetector):
	NAME = "GitHub"

	@classmethod
	def detect(cls, uri: ParseResult) -> typing.Optional[URIDetectorInternalUriReprT]:
		nl = uri.netloc.lower()

		namespace = None
		repoName = None
		branch = None
		path = None
		iD = None

		def genDict(uriType: URIType):
			return {
				"namespace": namespace,
				"repoName": repoName,
				"branch": branch,
				"path": PurePosixPath._from_parts(path) if path else None,
				"uriType": uriType,
				"id": iD if iD else None,
			}

		if nl in {"www.github.com", "github.com", "raw.githubusercontent.com"}:
			parts = PurePosixPath(uri.path)._parts
			if parts and parts[0] == "/":
				namespace, repoName = parts[1:3]

				if len(parts) == 3:
					return genDict(URIType.root)
				else:
					if nl.endswith("github.com"):
						if parts[3] in {"blob", "tree"}:
							branch = parts[4]

							if parts[3] == "blob":
								path = parts[5:]
							return genDict(URIType.file)
						elif parts[3] == "issues":
							iD = int(parts[4]) if len(parts) > 4 else None
							return genDict(URIType.bug)
						elif parts[3] == "releases":
							if len(parts) > 5:
								if parts[4] == "tag":
									branch = parts[5]
							return genDict(URIType.release)
						elif parts[3] == "tags":
							return genDict(URIType.release)
						elif parts[3] == "wiki":
							path = parts[4:]
							return genDict(URIType.wiki)
					else:  # raw.githubusercontent.com
						branch = parts[3]
						path = parts[4:]
						return genDict(URIType.file)
		elif nl.endswith(".github.io"):
			nl = nl.split(".")[:-2]
			if len(nl) == 1:
				namespace = nl[0]
				parts = PurePosixPath(uri.path)._parts
				if parts and parts[0] == "/" and len(parts) >= 2:
					repoName = parts[1]
					branch = "gh-pages"
					path = parts[2:]
					return genDict(URIType.page)

try:
	from GitLabInstancesDataset import isGitLab
except ImportError:
	from warnings import warn
	warn("Install GitLabInstancesDataset")
	def isGitLab(domain: typing.Union[str]) -> bool:
		return domain in {"gitlab.com", "foss.heptapod.net"}


class GitLabURIDetector(URIDetector):
	NAME = "GitLab"

	@classmethod
	def parsePrefixSuffix(cls, parts):
		try:
			dashIndex = parts.index("-")
		except ValueError:
			prefix = parts
			suffix = []
		else:
			prefix = parts[:dashIndex]
			suffix = parts[dashIndex + 1:]
		return prefix, suffix

	@classmethod
	def detect(cls, uri: ParseResult) -> typing.Optional[URIDetectorInternalUriReprT]:
		nl = uri.netloc.lower()

		if not isGitLab(nl):
			return None

		namespace, suffix = cls.parsePrefixSuffix(PurePosixPath(uri.path)._parts)
		if namespace and namespace[0] == "/":
			namespace = namespace[1:]

		repoName = namespace[-1]
		namespace = namespace[:-1]
		branch = None
		path = None
		iD = None

		def genDict(uriType: URIType):
			return {
				"netloc": nl,
				"namespace": namespace,
				"repoName": repoName,
				"branch": branch,
				"path": PurePosixPath._from_parts(path) if path else None,
				"uriType": uriType,
				"id": iD if iD else None,
			}

		if not suffix:
			return genDict(URIType.root)
		else:
			if suffix[0] in {"blob", "tree", "raw"}:
				if len(suffix) >= 2:
					branch = suffix[1]

					if suffix[0] in {"blob", "raw"}:
						path = suffix[2:]
					return genDict(URIType.file)
			elif suffix[0] == "issues":
				iD = int(suffix[1]) if len(suffix) > 2 else None
				return genDict(URIType.bug)
			elif suffix[0] == "releases":
				if len(suffix) > 5:
					if suffix[1] == "tag":
						branch = suffix[2]
				return genDict(URIType.release)
			elif suffix[0] == "releases":
				return genDict(URIType.release)
			elif suffix[0] == "wikis":
				path = parts[1:]
				return genDict(URIType.wiki)
