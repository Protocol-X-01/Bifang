TOKEN_FACTORY_ROLES = {
    "fast": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
    "balanced": "nvidia/nemotron-3-super-120b-a12b",
    "reasoning": "nvidia/Nemotron-3-Ultra-550b-a55b",
}

NVIDIA_INTEGRATE_ROLES = {
    "fast": "nvidia/nemotron-3-nano-30b-a3b",
    "balanced": "nvidia/nemotron-3-super-120b-a12b",
    "reasoning": "nvidia/nemotron-3-ultra-550b-a55b",
}

ZAI_ROLES = {
    "fast": "glm-5.3-flash",
    "balanced": "glm-5.3",
    "reasoning": "glm-5.3",
}

HUGGINGFACE_ROLES = {
    "fast": "Qwen/Qwen2.5-Coder-32B-Instruct",
    "balanced": "meta-llama/Llama-3.3-70B-Instruct",
    "reasoning": "deepseek-ai/DeepSeek-V3-0324",
}

PROVIDER_ROLES: dict[str, dict[str, str]] = {
    "nebius": TOKEN_FACTORY_ROLES,
    "nvidia": NVIDIA_INTEGRATE_ROLES,
    "zai": ZAI_ROLES,
    "huggingface": HUGGINGFACE_ROLES,
}
