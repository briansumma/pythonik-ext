from pythonik.specs.assets import AssetSpec as OriginalAssetSpec
from pythonik.specs.base import Spec as OriginalSpec
from pythonik.specs.collection import CollectionSpec as OriginalCollectionSpec
from pythonik.specs.files import FilesSpec as OriginalFilesSpec
from pythonik.specs.jobs import JobSpec as OriginalJobSpec
from pythonik.specs.metadata import MetadataSpec as OriginalMetadataSpec
from pythonik.specs.search import SearchSpec as OriginalSearchSpec

from ..utils import suppress_stdout


class QuietMixin(OriginalSpec):
    """Mixin that adds stdout suppression to any Spec class."""

    def send_request(self, *args, **kwargs):
        with suppress_stdout():
            return super().send_request(*args, **kwargs)

    @classmethod
    def parse_response(cls, *args, **kwargs):
        with suppress_stdout():
            return OriginalSpec.parse_response(*args, **kwargs)


class QuietAssetSpec(QuietMixin, OriginalAssetSpec):
    pass


AssetSpec = QuietAssetSpec


class QuietCollectionSpec(QuietMixin, OriginalCollectionSpec):
    pass


CollectionSpec = QuietCollectionSpec


class QuietFilesSpec(QuietMixin, OriginalFilesSpec):
    pass


FilesSpec = QuietFilesSpec


class QuietJobSpec(QuietMixin, OriginalJobSpec):
    pass


JobSpec = QuietJobSpec


class QuietMetadataSpec(QuietMixin, OriginalMetadataSpec):
    pass


MetadataSpec = QuietMetadataSpec


class QuietSearchSpec(QuietMixin, OriginalSearchSpec):
    pass


SearchSpec = QuietSearchSpec
