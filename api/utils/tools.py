import requests
import difflib
import json
import os
from typing import List, Dict, Union
from dotenv import load_dotenv

load_dotenv(".env.local")

CLIENT_ID = os.environ.get("ADOBE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("ADOBE_CLIENT_SECRET")
COMPANY_ID = os.environ.get("ADOBE_COMPANY_ID")
ORG_ID = os.environ.get("ADOBE_ORG_ID")
REPORTSUIT_ID = os.environ.get("ADOBE_REPORTSUIT_ID")


# === Get Access Token ===
def get_access_token():
    url = "https://ims-na1.adobelogin.com/ims/token/v3"

    payload = f"grant_type=client_credentials&client_id={CLIENT_ID}&client_secret={CLIENT_SECRET}&scope=openid%2CAdobeID%2Cadditional_info.projectedProductContext%2Ctarget_sdk%2Cread_organizations%2Cadditional_info.roles"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Cookie": "ftrset=611; relay=f0b5d32e-f7c3-480b-9ac3-8f08e5df8f94",
    }

    response = requests.request("POST", url, headers=headers, data=payload, timeout=3)

    return response.json()["access_token"]


with open(
    r"api\utils\metrics.json",
    "r",
    encoding="utf-8",
) as f:
    METRICS = json.load(f)

with open(
    r"api\utils\dimension.json",
    "r",
    encoding="utf-8",
) as f:
    DIMENSIONS = json.load(f)


def get_closest_match(name: str, items: list, key: str = "id") -> str:
    name = name.lower()
    matches = difflib.get_close_matches(name, items, n=1, cutoff=0.4)
    return matches[0] if matches else None


def get_report(
    metrics: Union[List[Dict[str, str]], Dict[str, str], str],
    dimension: str,
    start_date: str,
    end_date: str,
):
    """Fetch a report from Adobe Analytics via OAuth"""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json;charset=utf-8",
        "x-gw-ims-org-id": f"{ORG_ID}",
        "x-gw-ims-user-id": "7CC01F6C631C117E0A495CCE@80362013631c0cf6495fea.e",
        "x-proxy-global-company-id": f"{COMPANY_ID}",
        "x-request-id": "7ad7b64ed1b0465d8a6fba9a215bd4d0",
        "x-request-entity-id": "6578686f1a29784f54f2d788",
        "x-request-client-type": "AW",
        "Authorization": f"Bearer {get_access_token()}",
    }

    if isinstance(metrics, str):
        metrics = [{"id": metrics}]
    elif isinstance(metrics, dict):
        metrics = [metrics]

    metric_container = {"metrics": []}

    for index, metric in enumerate(metrics):
        metric_entry = {
            "columnId": str(index),
            "id": get_closest_match(metric["id"], METRICS),
        }
        metric_container["metrics"].append(metric_entry)

    valid_dimension = get_closest_match(dimension, DIMENSIONS)

    body = {
        "rsid": f"{REPORTSUIT_ID}",
        "globalFilters": [
            {
                "type": "dateRange",
                "dateRange": f"{start_date}T00:00:00/{end_date}T23:59:59",
            }
        ],
        "metricContainer": metric_container,
        "dimension": valid_dimension,
        "settings": {"limit": 10},
    }
    url = "https://appservice-reporting4-1.omniture.com/reporting/1.0/analytics/users/reports/ranked?locale=en_US"
    # url = "https://analytics.adobe.io/922aca57d4fe4cd290b1558b7271104d/hdfcba0/reports"

    try:
        res = requests.post(url, headers=headers, json=body, timeout=30)
        res.raise_for_status()
        # return res.json()
        return {"debug": {"headers": headers, "body": body}, "result": res.json()}

    except requests.exceptions.HTTPError as err:
        return {
            "error": f"{err.response.status_code} {err.response.reason}",
            "details": err.response.text,
        }
