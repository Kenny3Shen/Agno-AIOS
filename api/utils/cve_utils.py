import re
from loguru import logger

def parse_cve_markdown(text: str) -> list[dict[str, str]]:
    """
    解析 Markdown 文本，提取 CVE 信息。
    返回一个列表，每个元素是一个字典：
    {
        'cve_id': str,
        'description': str,
        'github_url': str
    }
    """
    if not text:
        logger.warning("parse_cve_markdown called with empty text")
        return []

    lines = text.strip().split("\n")
    cve_data = []
    current_cve = None
    current_desc = []

    # 正则表达式
    cve_pattern = re.compile(r"^##\s*(CVE-\d{4}-\d+)")
    url_pattern = re.compile(r"-\s*\[(https://github\.com/[^\]]+)\]")

    for line in lines:
        line = line.strip()

        # 匹配 CVE 标题
        cve_match = cve_pattern.match(line)
        if cve_match:
            if current_cve and not any(d["cve_id"] == current_cve for d in cve_data):
                cve_data.append(
                    {
                        "cve_id": current_cve,
                        "description": "\n".join(current_desc).strip(),
                        "github_url": "",
                    }
                )

            current_cve = cve_match.group(1)
            current_desc = []
            continue

        # 匹配 GitHub URL
        url_match = url_pattern.match(line)
        if url_match:
            if current_cve:
                url = url_match.group(1)
                cve_data.append(
                    {
                        "cve_id": current_cve,
                        "description": "\n".join(current_desc).strip(),
                        "github_url": url,
                    }
                )
            continue

        if (
            current_cve
            and not line.startswith("##")
            and not line.startswith("![")
            and line
        ):
            current_desc.append(line)

    if current_cve and not any(d["cve_id"] == current_cve for d in cve_data):
        cve_data.append(
            {
                "cve_id": current_cve,
                "description": "\n".join(current_desc).strip(),
                "github_url": "",
            }
        )

    return cve_data