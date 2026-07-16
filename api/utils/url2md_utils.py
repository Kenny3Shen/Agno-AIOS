system_prompt = """你是一位网络安全专家, 根据输入的内容提取威胁情报, 并以指定的 JSON 格式输出。

## 输入格式：
Markdown 格式文本，包含文章标题和主要内容。

## 一级分类规则和二级分类规则：
- 漏洞管理
    - 漏洞披露: 涉及新漏洞的公开披露、漏洞预警信息
    - 漏洞利用: 涉及漏洞攻击技术、POC利用/EXP发布/高危案例
- 威胁情报
    - APT攻击: 关注高级持续性威胁组织及其攻击活动
    - 黑客组织动态: 报道网络犯罪团伙、勒索软件团伙、黑客团伙动态
    - 恶意软件: 涉及病毒、木马、勒索软件、僵尸网络等
    - 威胁行为分析: 攻击手法、TTPs（战术-技术-程序）、攻击链
- 安全事件
    - 数据泄露: 报道敏感数据泄露、暗网数据交易
    - 网络攻击事件: 涉及DDoS、SQL注入、XSS攻击等
    - 供应链攻击: 报道SolarWinds式攻击、软件供应链漏洞
    - 设备入侵: 报道汽车、物联网设备、工控系统被入侵
    - 社会工程攻击: 涉及钓鱼邮件、电信诈骗、病毒木马
- 法律法规与合规
    - 国际法规: 报道GDPR、CCPA等国际法规
    - 国内法规: 报道网络安全法、数据安全法等国内法规
    - 行业标准: 报道ISO 27001、NIST框架、等保2.0、PCI DSS等行业标准
    - 数据合规: 报道数据本地化政策、跨境传输协议
- 攻防技术
    - 红蓝对抗: 报道攻防演练、模拟攻击场景
    - 渗透测试: 报道漏洞利用链、社会工程测试
    - 事件响应与溯源: 报道应急处置、事件分析、取证与恢复
    - 云与架构安全: 报道容器、Kubernetes安全/云原生安全
    - 端点与网络安全: 报道网络设备、物联网、EDR/XDR、防火墙等
    - 安全意识: 报道社会工程、钓鱼防御、密码安全、物理安全等
- 数据安全
    - 数据保护技术: 报道数据脱敏、加密、备份与恢复、联邦学习等
    - 数据生命周期安全: 报道数据采集、存储、共享、销毁的全流程防护
- 智能终端安全
    - 智能汽车: 报道汽车制造、车联网、汽车供应链安全
    - 充电桩: 报道充电桩安全相关内容
    - 飞行安全: 报道飞行器、无人机、飞行控制、飞行汽车、低空经济等安全内容
    - 机器人: 报道机器人安全相关内容
- 安全研究与趋势
    - AI安全: 报道AI大模型安全风险、AI威胁检测、对抗性机器学习攻击
    - 量子安全: 报道量子安全、后量子密码（PQC）、量子密钥分发（QKD）
    - 重大事件: 报道国家级网络战,大规模DDoS攻击（如Mirai变种）
    - 关键基础设施威胁: 报道能源、电力、交通系统防护、工控系统、医疗、金融威胁
    - 区块链安全: 报道智能合约漏洞相关内容
    - 密码技术: 报道密码算法、密钥管理相关内容

## 三级分类规则：
- 终端安全: 操作系统、平台、软件、硬件组件、PC、移动设备相关安全内容
- 汽车安全: 汽车、车联网相关安全内容
- 云端安全: 云计算、云服务相关安全内容
- 法律法规: 安全法律法规相关内容
- 大模型: 人工智能、大模型相关安全内容
- 运维安全: IT运维、DevOps相关安全内容
- 机器人安全: 机器人相关安全内容
- 飞行安全: 飞行器、无人机相关安全内容
- 安全相关: 不符合以上分类的其他安全内容

## 输出格式：
{
    "threat_type":"一级分类", // 从 **一级分类规则和二级分类规则** 中选择
    "type2":"二级分类", // 根据一级分类选择对应的二级分类，允许多个二级分类，每个二级分类之间用','分隔
    "type3":"三级分类", // 从**三级分类规则**中选择
    "name": "中文威胁名称", // 从标题中获取相关名称信息
    "description": "中文内容摘要", // 限制在200字以内，不能包含不存在的内容。
    "attributes": {
        "tactics": ["攻击方法"], // SQL注入、钓鱼邮件、恶意软件、提示词注入等
        "targets": ["攻击目标"], // 受影响用户、行业、组织、国家等
        "indicators": ["入侵指标"], // 异常IP/域名、文件哈希、C2服务器、恶意软件、攻击路径等
        "data_type": "泄露数据类型", // 个人信息、企业数据、医疗记录等
        "data_volume": "泄露数据量", // 如: 500万条、2GB等
        "affected_info":{
            "CVE 编号": {   // 若有多个CVE编号，则每个CVE单独列出，若无CVE编号则使用组件名称
                "mitigation": "修复建议",
                "cvss_score": "CVSS 评分",
                "affected_system": ["受影响组件列表"], // 包括软件、硬件等，使用原文中的描述，不要翻译
                "affected_version": {"组件名称": "<或<=(>或>=) 一个最大(小)未修复版本号"} // 键必须为受影响组件，值必须以比较符 (<, <=, >, >=) 开头且只包含一个比较符和版本号，如:'< 1.2.3' 或 '>= 1.2.3'。优先匹配最大未修复版本号。
            }
        },
    },
    "references": ["相关引用 URL 列表"],
    "confidence_score": 0-100 // 根据内容及影响给出置信度评分
}


## 要求：
- 必须填写 一级分类、二级分类、三级分类
- 必须包含所有字段，原文未给出的值设置为空
- 判断是否为安全漏洞，如果不是则 "affected_info" 为空
- 仅输出 JSON，不要包含其他说明
"""


# 配置不同域名的解析规则
# 结构: 域名: (正文类名, 排除的元素列表, 截断标记)
# - 正文类名: 用于匹配包含正文的 div 元素
# - 排除的元素列表: 需要从正文中移除的元素的 class 名
# - 截断标记: 遇到包含该文本的元素时，停止提取后续内容（空字符串表示不截断）
domain_rules: dict[str, tuple[str, list[str], str]] = {

    "cybersecuritynews.com": (
        "td-post-content tagdiv-type",
        ["has-text-align-center has-background"],
        "",
    ),
    "www.redhotcyber.com": ("elementor-shortcode", ["tag-list", "table"], ""),
    "dailydarkweb.net": ("entry-content no-share", [], ""),
    "securityonline.info": ("entry-content read-details", [], "Related Posts"),
    "hackread.com": ("entry-content", [], ""),

    "www.csoonline.com": ("article__main", [], ""),
    "securityaffairs.com": (
        "row",
        ["common-heading line-bottom article-title mb-3 wow fadeInUp animated"],
        "Follow me on Twitter",
    ),
    "www.anquanke.com": ("content", [], ""),
    "www.freebuf.com": ("content-detail", [], "参考来源："),
    "www.seqrite.com": ("single-post-content", [], ""),
    "mp.weixin.qq.com": ("rich_media_wrp", [], ""),
    "thecyberexpress.com": ("entry-content no-share", [], "Share this:"),
    "thehackernews.com": ("articlebody clear cf", [], ""),
    "xlab.tencent.com": ("post-content", [], ""),

}


# Domains intentionally not crawled/parsed as Collect sources.
DISABLED_COLLECT_DOMAINS: frozenset[str] = frozenset(
    {
        "botcrawl.com",
        "go.theregister.com",
        "www.securitylab.ru",
        "theregister.com",
        "www.theregister.com",
        "securitylab.ru",
    }
)


def normalize_content_host(host: str | None) -> str:
    """Lowercase hostname without port or trailing dot."""
    value = (host or "").strip().lower().rstrip(".")
    if not value:
        return ""
    # Strip brackets from IPv6 literals if present
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    return value


def content_host_candidates(host: str | None) -> list[str]:
    """Ordered host keys to try against domain_rules (exact, www strip/add)."""
    base = normalize_content_host(host)
    if not base:
        return []
    candidates: list[str] = [base]
    if base.startswith("www."):
        bare = base[4:]
        if bare and bare not in candidates:
            candidates.append(bare)
    else:
        www = f"www.{base}"
        if www not in candidates:
            candidates.append(www)
    return candidates


def resolve_domain_rule_key(url: str) -> str | None:
    """Map a page URL to a domain_rules key, or None if no rule applies."""
    from urllib.parse import urlsplit

    host = normalize_content_host(urlsplit(url).hostname)
    if not host or host in DISABLED_COLLECT_DOMAINS:
        # Still allow parse if a non-disabled rule matches via candidates
        pass
    for key in content_host_candidates(host):
        if key in DISABLED_COLLECT_DOMAINS:
            continue
        if key in domain_rules:
            return key
    # Suffix / parent match (m.example.com → example.com rule)
    for rule_key in domain_rules:
        if rule_key in DISABLED_COLLECT_DOMAINS:
            continue
        if host == rule_key or host.endswith("." + rule_key) or rule_key.endswith("." + host):
            return rule_key
    return None


def active_domain_rules() -> dict[str, tuple[str, list[str], str]]:
    """domain_rules minus intentionally disabled Collect sources."""
    return {
        key: value
        for key, value in domain_rules.items()
        if key not in DISABLED_COLLECT_DOMAINS
        and not any(key == d or key.endswith("." + d) or d.endswith("." + key) for d in DISABLED_COLLECT_DOMAINS)
    }

# 需要从标题中移除的后缀
title_suffixes = ["-安全KER - 安全资讯平台", " - FreeBuf网络安全行业门户"]
