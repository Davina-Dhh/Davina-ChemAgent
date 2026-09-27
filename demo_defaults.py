"""公网演示默认配置（已按需求提交到仓库，访客无需再填 Key）。"""

# Agnes OpenAI 兼容
OPENAI_API_KEY = "sk-vGB7LmkeUFYcQTgRfRH5ECY3ZHNlVizuxcN0u3ElLLFGDH7q"
OPENAI_API_BASE = "https://apihub.agnes-ai.com/v1"
CHEMCROW_MODEL = "agnes-2.5-flash"

# Cloud 自动发现本机隧道地址（keep_t5_online.py 会更新并 push）
REACTIONT5_DISCOVERY_URL = (
    "https://raw.githubusercontent.com/Davina-Dhh/Davina-ChemAgent/"
    "main/static/t5_endpoint.json"
)
