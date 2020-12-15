from .uriDetector import GitHubURIDetector, GitLabURIDetector, URIDetectorInternalUriReprT


class CodeHostingRepoURINormalizer:
	DETECTOR = None

	@classmethod
	def makeSourceSpecPart(cls, uri: URIDetectorInternalUriReprT):
		raise NotImplementedError

	@classmethod
	def normalize(cls, uri):
		uri = cls.DETECTOR.detect(uri)
		if uri is not None:
			return cls.makeSourceSpecPart(uri)


class GitHubRepoURINormalizer(CodeHostingRepoURINormalizer):
	DETECTOR = GitHubURIDetector

	@classmethod
	def makeSourceSpecPart(cls, uri: URIDetectorInternalUriReprT):
		return "https://github.com/" + uri["namespace"] + "/" + uri["repoName"] + ".git"


class GitLabRepoURINormalizer(CodeHostingRepoURINormalizer):
	DETECTOR = GitLabURIDetector

	@classmethod
	def makeSourceSpecPart(cls, uri: URIDetectorInternalUriReprT):
		return "https://" + uri["netloc"] + "/" + "/".join(uri["namespace"]) + "/" + uri["repoName"]

normalizers = (
	GitHubRepoURINormalizer,
	GitLabRepoURINormalizer,
)
