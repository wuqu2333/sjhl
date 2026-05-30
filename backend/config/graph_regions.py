GRAPH_REGIONS = {
    "cn": {
        "label": "世纪互联",
        "graphBaseUrl": "https://microsoftgraph.chinacloudapi.cn/v1.0",
        "authBaseUrl": "https://login.partner.microsoftonline.cn",
    },
    "global": {
        "label": "全球",
        "graphBaseUrl": "https://graph.microsoft.com/v1.0",
        "authBaseUrl": "https://login.microsoftonline.com",
    },
    "us": {
        "label": "美国政府",
        "graphBaseUrl": "https://graph.microsoft.us/v1.0",
        "authBaseUrl": "https://login.microsoftonline.us",
    },
    "de": {
        "label": "德国",
        "graphBaseUrl": "https://graph.microsoft.de/v1.0",
        "authBaseUrl": "https://login.microsoftonline.de",
    },
}


def resolve_graph_region(region: str = "cn") -> dict[str, str]:
    return GRAPH_REGIONS.get(region or "cn", GRAPH_REGIONS["cn"])
