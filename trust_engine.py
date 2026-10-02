import base64
import hashlib
import json
import logging
import os
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Safe Async HTTP Client Import
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    import requests
    HAS_HTTPX = False

# Safe Config Import
try:
    from config import settings
except ImportError:
    settings = None

logger = logging.getLogger(__name__)


class TrustEngine:
    """Enterprise-Grade GitHub Signal Verification Audit Trail Engine.

    Features cryptographic SHA-256 hashing, dynamic monthly file rotation,
    internal SHA conflict race-condition resolution, robust key alias resolution,
    and fallback HTTP support.
    """

    def __init__(
        self,
        github_token: Optional[str] = None,
        repo_owner: Optional[str] = None,
        repo_name: Optional[str] = None,
        branch: Optional[str] = None,
        file_path: Optional[str] = None,
    ):
        # Credential key mapping with fallbacks
        self.github_token = (
            github_token
            or getattr(settings, "GITHUB_TOKEN", "")
            or getattr(settings, "TOKEN", "")
            or os.getenv("GITHUB_TOKEN", "")
            or os.getenv("TOKEN", "")
        )
        self.repo_owner = (
            repo_owner
            or getattr(settings, "REPO_OWNER", "")
            or getattr(settings, "GITHUB_REPO_OWNER", "")
            or os.getenv("REPO_OWNER", "")
            or os.getenv("GITHUB_REPO_OWNER", "")
        )
        self.repo_name = (
            repo_name
            or getattr(settings, "REPO_NAME", "")
            or getattr(settings, "GITHUB_REPO_NAME", "")
            or os.getenv("REPO_NAME", "")
            or os.getenv("GITHUB_REPO_NAME", "")
        )

        self.branch = (
            branch
            or getattr(settings, "GITHUB_BRANCH", "")
            or os.getenv("GITHUB_BRANCH", "main")
        )

        # Fix #2: Python 3.12+ safe timezone-aware UTC datetime
        if not file_path:
            month_str = datetime.now(timezone.utc).strftime("%Y_%m")
            self.file_path = f"signals/log_{month_str}.json"
        else:
            self.file_path = file_path

    def _get_api_url(self, target_file_path: Optional[str] = None) -> str:
        """Dynamic API URL builder for repository content."""
        path = target_file_path or self.file_path
        if not self.repo_owner or not self.repo_name:
            raise ValueError("[TRUST ENGINE ERROR] Repository owner or name is unconfigured!")
        return f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/contents/{path}"

    def generate_signal_hash(self, signal_data: Dict[str, Any]) -> str:
        """Generates cryptographic SHA-256 hash for signal verification."""
        sig_id = str(signal_data.get("id", ""))
        timestamp = str(signal_data.get("timestamp", ""))

        asset = str(signal_data.get("asset") or signal_data.get("symbol", "UNKNOWN"))
        direction = str(signal_data.get("direction") or signal_data.get("action", "HOLD"))
        score = str(signal_data.get("score") or signal_data.get("score_str", "0/10"))

        raw_string = f"{sig_id}|{timestamp}|{asset}|{direction}|{score}"
        return hashlib.sha256(raw_string.encode("utf-8")).hexdigest()

    async def commit_to_github(
        self,
        signal_data: Dict[str, Any],
        signal_hash: Optional[str] = None,
        max_retries: int = 3,
    ) -> str:
        """Asynchronously commits with internal retry logic for SHA conflicts."""
        if not self.github_token:
            raise ValueError("[TRUST ENGINE ERROR] GitHub token missing in config/env!")

        if not signal_hash:
            signal_hash = self.generate_signal_hash(signal_data)

        api_url = self._get_api_url()

        # Auth Header
        token_prefix = "Bearer" if self.github_token.startswith("github_pat_") else "token"
        headers = {
            "Authorization": f"{token_prefix} {self.github_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        sig_id = str(signal_data.get("id", ""))
        timestamp = str(signal_data.get("timestamp", ""))
        asset = str(signal_data.get("asset") or signal_data.get("symbol", "UNKNOWN"))
        direction = str(signal_data.get("direction") or signal_data.get("action", "HOLD"))
        score = str(signal_data.get("score") or signal_data.get("score_str", "0/10"))

        log_entry = {
            "id": sig_id,
            "timestamp": timestamp,
            "asset": asset,
            "direction": direction,
            "score": score,
            "hash": signal_hash,
        }

        # Fix #1: Include branch parameter in GET requests to prevent SHA mismatches
        get_api_url = f"{api_url}?ref={self.branch}"

        for attempt in range(1, max_retries + 1):
            try:
                if HAS_HTTPX:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        file_sha = None
                        existing_content = []

                        get_resp = await client.get(get_api_url, headers=headers)
                        if get_resp.status_code == 200:
                            file_info = get_resp.json()
                            file_sha = file_info.get("sha")
                            
                            raw_b64 = file_info.get("content", "").replace("\n", "").replace("\r", "")
                            if raw_b64:
                                try:
                                    decoded_bytes = base64.b64decode(raw_b64)
                                    parsed = json.loads(decoded_bytes.decode("utf-8"))
                                    if isinstance(parsed, list):
                                        existing_content = parsed
                                except (json.JSONDecodeError, Exception) as parse_err:
                                    # Fix #3: Safe JSON decode handling for corrupted/empty files
                                    logger.warning(f"Failed to parse existing log file JSON, starting fresh: {parse_err}")
                                    existing_content = []
                        elif get_resp.status_code != 404:
                            logger.warning(
                                f"GitHub GET Fetch Warning [{get_resp.status_code}]: {get_resp.text}"
                            )

                        # Fix #4: Prevent duplicate entries for the same signal ID
                        if not any(item.get("id") == sig_id for item in existing_content):
                            existing_content.append(log_entry)

                        json_bytes = json.dumps(existing_content, indent=2).encode("utf-8")
                        encoded_content = base64.b64encode(json_bytes).decode("utf-8")

                        payload = {
                            "message": f"Log signal {sig_id} - Hash: {signal_hash[:8]}",
                            "content": encoded_content,
                            "branch": self.branch,
                        }
                        if file_sha:
                            payload["sha"] = file_sha

                        put_resp = await client.put(api_url, headers=headers, json=payload)

                        if put_resp.status_code in [200, 201]:
                            commit_info = put_resp.json()
                            commit_url = commit_info.get("commit", {}).get("html_url", "")
                            logger.info(
                                f"[TRUST ENGINE SUCCESS] Verified signal {sig_id} on GitHub: {commit_url}"
                            )
                            return commit_url

                        if put_resp.status_code in [409, 422] and attempt < max_retries:
                            logger.warning(
                                f"[RACE CONDITION DETECTED] GitHub SHA conflict (Attempt {attempt}/{max_retries}). Retrying..."
                            )
                            await asyncio.sleep(0.5 * attempt)
                            continue

                        raise RuntimeError(
                            f"GitHub API Error [{put_resp.status_code}]: {put_resp.text}"
                        )
                else:
                    # Sync fallback execution using thread
                    def _sync_commit():
                        file_sha_sync = None
                        existing_sync = []

                        get_resp = requests.get(get_api_url, headers=headers, timeout=10)
                        if get_resp.status_code == 200:
                            file_info = get_resp.json()
                            file_sha_sync = file_info.get("sha")
                            raw_b64 = file_info.get("content", "").replace("\n", "").replace("\r", "")
                            if raw_b64:
                                try:
                                    parsed = json.loads(base64.b64decode(raw_b64).decode("utf-8"))
                                    if isinstance(parsed, list):
                                        existing_sync = parsed
                                except Exception:
                                    existing_sync = []

                        if not any(item.get("id") == sig_id for item in existing_sync):
                            existing_sync.append(log_entry)

                        json_bytes = json.dumps(existing_sync, indent=2).encode("utf-8")
                        encoded_content = base64.b64encode(json_bytes).decode("utf-8")

                        payload = {
                            "message": f"Log signal {sig_id} - Hash: {signal_hash[:8]}",
                            "content": encoded_content,
                            "branch": self.branch,
                        }
                        if file_sha_sync:
                            payload["sha"] = file_sha_sync

                        put_resp = requests.put(api_url, headers=headers, json=payload, timeout=10)
                        if put_resp.status_code in [200, 201]:
                            return put_resp.json().get("commit", {}).get("html_url", "")
                        
                        if put_resp.status_code in [409, 422] and attempt < max_retries:
                            raise KeyError("Conflict")

                        raise RuntimeError(f"GitHub API Error [{put_resp.status_code}]: {put_resp.text}")

                    try:
                        return await asyncio.to_thread(_sync_commit)
                    except KeyError:
                        await asyncio.sleep(0.5 * attempt)
                        continue

            except Exception as err:
                logger.warning(f"[TRUST ENGINE RETRY] Attempt {attempt}/{max_retries} failed: {err}")
                if attempt == max_retries:
                    raise err
                await asyncio.sleep(0.5 * attempt)

        raise RuntimeError("[TRUST ENGINE FAIL] Exceeded maximum commit retries.")


if __name__ == "__main__":
    async def test_trust_engine():
        print("--- Testing Optimized Enterprise TrustEngine ---")
        engine = TrustEngine(
            github_token="mock_token",
            repo_owner="demo_user",
            repo_name="demo_repo",
        )

        sample_signal = {
            "id": "SIG_1001",
            "timestamp": "2026-10-01T12:00:00Z",
            "symbol": "EURUSD_otc",
            "action": "CALL",
            "score_str": "8.5/10",
        }

        sig_hash = engine.generate_signal_hash(sample_signal)
        print(f"Generated Hash: {sig_hash}")
        print(f"Log File Path: {engine.file_path}")

    asyncio.run(test_trust_engine())