import hashlib
import json
import time
import os
import requests

class TrustEngine:
    def __init__(self, github_token: str, repo_owner: str, repo_name: str, file_path: str = "signals/log.json"):
        self.github_token = github_token
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.file_path = file_path
        self.api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"

    def generate_signal_hash(self, signal_data: dict) -> str:
        """
        সিগন্যাল ডেটা থেকে SHA-256 Hash তৈরি করে।
        """
        # ডেটা কনসিস্টেন্সি বজায় রাখতে deterministic string তৈরি
        raw_string = f"{signal_data['id']}|{signal_data['timestamp']}|{signal_data['asset']}|{signal_data['direction']}|{signal_data['score']}"
        signal_hash = hashlib.sha256(raw_string.encode('utf-8')).hexdigest()
        return signal_hash

    def commit_to_github(self, signal_data: dict, signal_hash: str) -> str:
        """
        গিটহাব রেপোতে সিগন্যাল লগ কমিট করে এবং Commit SHA/URL ফেরত দেয়।
        """
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }

        # ১. বর্তমান ফাইলের SHA আনা (যদি ফাইল আগে থেকে থাকে)
        get_resp = requests.get(self.api_url, headers=headers)
        file_sha = None
        existing_content = []

        if get_resp.status_code == 200:
            file_info = get_resp.json()
            file_sha = file_info.get("sha")
            # আগের কন্টেন্ট ডিকোড করা
            import base64
            decoded_bytes = base64.b64decode(file_info["content"])
            existing_content = json.loads(decoded_bytes.decode('utf-8'))

        # ২. নতুন সিগন্যাল রেকর্ড যুক্ত করা
        log_entry = {
            "id": signal_data["id"],
            "timestamp": signal_data["timestamp"],
            "asset": signal_data["asset"],
            "direction": signal_data["direction"],
            "score": signal_data["score"],
            "hash": signal_hash
        }
        existing_content.append(log_entry)

        # ৩. গিটহাবের জন্য কন্টেন্ট বেস৬৪ এনকোড করা
        updated_json_bytes = json.dumps(existing_content, indent=2).encode('utf-8')
        import base64
        encoded_content = base64.b64encode(updated_json_bytes).decode('utf-8')

        payload = {
            "message": f"Log signal {signal_data['id']} - Hash: {signal_hash[:8]}",
            "content": encoded_content,
            "branch": "main"
        }
        if file_sha:
            payload["sha"] = file_sha

        # ৪. Commit রিকোয়েস্ট পাঠানো
        put_resp = requests.put(self.api_url, headers=headers, json=payload)
        
        if put_resp.status_code in [200, 201]:
            commit_info = put_resp.json()
            return commit_info["commit"]["html_url"]
        else:
            print(f"[TrustEngine Error] GitHub API failed: {put_resp.text}")
            return None