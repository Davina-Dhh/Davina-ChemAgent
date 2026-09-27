"""公网演示默认配置（已按需求提交到仓库，访客无需再填 Key）。"""

# Agnes OpenAI 兼容
OPENAI_API_KEY = "sk-vGB7LmkeUFYcQTgRfRH5ECY3ZHNlVizuxcN0u3ElLLFGDH7q"
OPENAI_API_BASE = "https://apihub.agnes-ai.com/v1"
CHEMCROW_MODEL = "agnes-2.5-flash"

# Cloud 自动发现本机隧道地址（keep_t5_online.py 会更新并 push）
# 优先 jsDelivr：国内/部分网络对 raw.githubusercontent.com 缓存极旧
REACTIONT5_DISCOVERY_URL = (
    "https://cdn.jsdelivr.net/gh/Davina-Dhh/Davina-ChemAgent@main/"
    "static/t5_endpoint.json"
)
