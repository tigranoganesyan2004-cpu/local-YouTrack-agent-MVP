from __future__ import annotations

import requests

from src.config import YOUTRACK_BASE_URL, YOUTRACK_TOKEN


class YouTrackClient:
    """    Заготовка под будущую интеграцию.
    Это не включено в текущий MVP по файлам, но архитектурно уже готово.

    Логика:
    1. получить список issues;
    2. получить details + customFields;
    3. получить links;
    4. получить attachments;
    5. положить это в локальный кэш;
    6. затем запускать ту же подготовку/индексацию.
    """

    def __init__(self, base_url: str = YOUTRACK_BASE_URL, token: str = YOUTRACK_TOKEN):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.session = requests.Session()
        if token:
            self.session.headers.update({
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            })

    def _check(self):
        if not self.base_url or not self.token:
            raise ValueError("Нужно заполнить YOUTRACK_BASE_URL и YOUTRACK_TOKEN в .env")

    def fetch_issues(self, query: str = "", top: int = 100, skip: int = 0):
        self._check()
        fields = (
            "id,idReadable,summary,description,created,updated,resolved,"
            "customFields(name,value(name,text,presentation,date)),"
            "commentsCount,votes"
        )
        url = f"{self.base_url}/api/issues"
        params = {
            "query": query,
            "$top": top,
            "$skip": skip,
            "fields": fields,
        }
        response = self.session.get(url, params=params, timeout=120)
        response.raise_for_status()
        return response.json()

    def fetch_issue_links(self, issue_id: str):
        self._check()
        fields = "id,direction,linkType(name,sourceToTarget,targetToSource),issues(id,idReadable,summary)"
        url = f"{self.base_url}/api/issues/{issue_id}/links"
        response = self.session.get(url, params={"fields": fields}, timeout=120)
        response.raise_for_status()
        return response.json()

    def fetch_issue_attachments(self, issue_id: str):
        self._check()
        fields = "id,name,size,mimeType,extension,url,created,updated"
        url = f"{self.base_url}/api/issues/{issue_id}/attachments"
        response = self.session.get(url, params={"fields": fields}, timeout=120)
        response.raise_for_status()
        return response.json()

    def download_attachment(self, attachment_url: str, out_path: str):
        self._check()
        response = self.session.get(attachment_url, timeout=240)
        response.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(response.content)
