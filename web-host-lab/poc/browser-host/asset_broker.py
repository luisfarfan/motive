"""Immutable resource broker. Uses Element Lab v1; not an OS sandbox or firewall."""
import sys
sys.dont_write_bytecode = True
from pathlib import Path
from types import MappingProxyType
from dataclasses import dataclass

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO/'element-lab/sdk'))
from web_contract import validate_web

CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
       "connect-src 'none'; font-src 'none'; media-src 'none'; object-src 'none'; "
       "frame-src 'none'; worker-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")

@dataclass(frozen=True)
class Resource:
    data: bytes
    media_type: str
    headers: tuple

class AssetBroker:
    def __init__(self, directory: Path, instance: int, generation: int):
        if type(instance) is not int or type(generation) is not int or not (0 < instance <= 2**53-1 and 0 < generation <= 2**53-1):
            raise ValueError('IDENTITY')
        # Reuse the published schema, integrity and descriptor-relative no-follow
        # reads. The SDK's literal-source review is NOT a security boundary.
        manifest, report, files = validate_web(directory)
        self.origin = f'motive://i{instance}-g{generation}'
        headers = (('Content-Security-Policy', CSP), ('Cache-Control','no-store'),
                   ('X-Content-Type-Options','nosniff'),
                   ('Permissions-Policy','camera=(), microphone=(), geolocation=(), clipboard-read=(), clipboard-write=()'))
        media = {a['path']:a['media_type'] for a in manifest['assets']}
        self._resources = MappingProxyType({self.origin+'/'+p:Resource(bytes(data),media[p],headers) for p,data in files.items()})
        self.entry = self.origin+'/'+manifest['entry']
        self.report = MappingProxyType({**report,'broker':'immutable exact URL inventory','resources':len(files),'network_enforced':False})
        self._closed = False

    def request(self, url: str, method: str = 'GET') -> Resource | None:
        # No decoding, DNS, filesystem resolution, network fallback or URL regex.
        if self._closed or type(url) is not str or len(url)>512 or method != 'GET':
            return None
        return self._resources.get(url)

    def navigation(self, url: str, *, initial: bool, main_frame: bool) -> bool:
        return not self._closed and initial and main_frame and url == self.entry

    def close(self):
        self._closed = True
        self._resources = MappingProxyType({})

    @staticmethod
    def third_party_execution_allowed() -> bool:
        return False  # Native process/sandbox/egress acceptance is absent.
