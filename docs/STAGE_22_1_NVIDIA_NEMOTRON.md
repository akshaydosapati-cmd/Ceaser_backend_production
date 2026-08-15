# NVIDIA Nemotron provider

CEASER can route eligible requests to NVIDIA's OpenAI-compatible hosted NIM API.
Configure `NVIDIA_API_KEY`, `NVIDIA_BASE_URL`, and `NVIDIA_MODEL` on the server or
cloud worker. Credentials must never be exposed to desktop or browser clients.

The default model is `nvidia/nemotron-3-ultra-550b-a55b`. Its routing capabilities
are configuration metadata used by CEASER; they are not benchmark claims. Bolt
continues to request coding with reasoning and tool-use preferences, and the
ModelRouter remains responsible for selection and fallback.

Both direct NVIDIA and Hugging Face are restricted to the
`software_engineering` workload emitted by Bolt. Normal chat remains on the
existing normal-chat provider pool, led by OpenAI, and cannot fall through into
the coding-only provider pool.

NVIDIA Developer hosted endpoints are trial/development infrastructure. Their
availability, quotas, rate limits, and terms must be validated before commercial
production use. Production deployment should use an NVIDIA production endpoint,
partner endpoint, or self-hosted NIM with an appropriate service agreement.
