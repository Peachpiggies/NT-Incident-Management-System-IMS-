"""
Virus scanning utilities.

This module provides a small async wrapper around ClamAV's
INSTREAM protocol.

The scanner is intentionally fail-closed:
if ClamAV cannot be reached, the upload is rejected instead
of allowing an unscanned file into storage.
"""

from __future__ import annotations

import asyncio
import socket


class VirusScanError(RuntimeError):
    """Base exception for virus scanning failures."""


class VirusDetectedError(VirusScanError):
    """Raised when ClamAV detects malware."""

    def __init__(self, result: str) -> None:
        self.result = result
        super().__init__("Malicious content detected")


class VirusScannerUnavailableError(VirusScanError):
    """Raised when the virus scanner cannot be reached."""


# ClamAV INSTREAM protocol limits chunks to 4 KiB.
_CHUNK_SIZE = 4096
_SOCKET_TIMEOUT = 10.0


def _scan_with_clamav(
    content: bytes,
    host: str,
    port: int,
    timeout: float,
) -> str:
    """
    Scan bytes using ClamAV's INSTREAM protocol.

    Returns:
        "OK" when the file is clean.

    Raises:
        VirusDetectedError:
            When ClamAV reports a virus.
        VirusScannerUnavailableError:
            When ClamAV cannot be reached or returns an invalid response.
    """

    try:
        with socket.create_connection(
            (host, port),
            timeout=timeout,
        ) as sock:
            sock.settimeout(timeout)

            # Start INSTREAM command.
            sock.sendall(b"zINSTREAM\0")

            # Send content in chunks.
            for offset in range(0, len(content), _CHUNK_SIZE):
                chunk = content[offset : offset + _CHUNK_SIZE]

                # ClamAV expects a 4-byte big-endian chunk size.
                sock.sendall(len(chunk).to_bytes(4, byteorder="big"))
                sock.sendall(chunk)

            # Zero-length chunk terminates the stream.
            sock.sendall((0).to_bytes(4, byteorder="big"))

            response = sock.recv(4096)

    except (OSError, TimeoutError) as exc:
        raise VirusScannerUnavailableError(
            "Virus scanner is unavailable"
        ) from exc

    if not response:
        raise VirusScannerUnavailableError(
            "Virus scanner returned an empty response"
        )

    result = response.decode("utf-8", errors="replace").strip()

    # Typical responses:
    #
    # stream: OK
    # stream: Eicar-Test-Signature FOUND
    #
    if result.endswith("FOUND"):
        raise VirusDetectedError(result)

    if not result.endswith("OK"):
        raise VirusScannerUnavailableError(
            "Virus scanner returned an unexpected response"
        )

    return "OK"


async def scan_bytes(
    content: bytes,
    *,
    host: str = "127.0.0.1",
    port: int = 3310,
    timeout: float = _SOCKET_TIMEOUT,
) -> None:
    """
    Scan file content asynchronously.

    The synchronous socket operation is executed in a worker thread
    so it does not block FastAPI's event loop.

    Raises:
        VirusDetectedError:
            File contains malicious content.

        VirusScannerUnavailableError:
            ClamAV is unavailable or returned an invalid response.
    """

    if not content:
        raise VirusScanError("Cannot scan empty content")

    await asyncio.to_thread(
        _scan_with_clamav,
        content,
        host,
        port,
        timeout,
    )