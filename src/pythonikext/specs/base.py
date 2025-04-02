"""Base spec extensions for pythonik."""

from typing import Optional, Type

from pydantic import BaseModel
from pythonik.models.base import Response as PythonikResponse
from pythonik.specs.base import Spec as OriginalSpecBase
from requests import Request, Response

from .._logging import configure_logging, get_logger

# Configure logging with defaults
configure_logging()
logger = get_logger(__name__)


class ExtendedSpecBase(OriginalSpecBase):
    """
    Base class for extended specs with improved logging and error handling.

    This class enhances the original Pythonik spec base with:
    - Better logging using the logging module instead of print statements
    - Improved error handling and request preparation
    """

    @staticmethod
    def parse_response(
        response: Response,
        model: Optional[Type[BaseModel]] = None
    ) -> PythonikResponse:
        """
        Enhanced response parser that uses logging instead of print statements.

        Args:
            response: The HTTP response from the API
            model: Optional Pydantic model to validate the response against

        Returns:
            PythonikResponse object containing the parsed response
        """
        if response.ok:
            logger.debug(response.text)
            if model:
                data = response.json()
                model_instance = model.model_validate(data)
                return PythonikResponse(response=response, data=model_instance)

        return PythonikResponse(response=response, data=None)

    def send_request(self, method, path, **kwargs) -> Response:
        """
        Enhanced request sender with better logging.

        Args:
            method: HTTP method to use
            path: API endpoint path
            **kwargs: Additional arguments to pass to the request

        Returns:
            Response object from the API
        """
        url = self.gen_url(path)
        logger.debug("Sending %s request to %s", method, url)

        request = self._prepare_request(method, url, **kwargs)
        response = self.session.send(request, timeout=self.timeout)

        return response

    def _prepare_request(self, method, url, **kwargs):
        """Prepare the request object."""
        request = Request(
            method=method, url=url, headers=self.session.headers, **kwargs
        )
        return self.session.prepare_request(request)
