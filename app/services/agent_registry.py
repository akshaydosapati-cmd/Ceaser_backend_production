DEFAULT_AGENT_MODULES: dict[str, list[str]] = {
    "Bolt": ["Tasks", "Scheduling", "Reminders", "Automation", "Workflow Execution", "Follow-Ups"],
    "Alex": ["Goals", "Productivity", "Learning", "Health", "Travel", "Finance"],
    "Friday": ["Instagram", "LinkedIn", "YouTube", "Blog", "Email", "Content Planning"],
    "Zeus": ["CEO", "CTO", "CFO", "COO", "Marketing", "Sales", "Analytics", "HR"],
    "Nova": ["Research", "Competitor Analysis", "Market Research", "Trend Monitoring", "Reports"],
    "Atlas": ["Planning", "Architecture", "Coding", "Infrastructure", "DevOps", "Debugging", "Code Review", "Deployment", "GitHub Management", "VS Code Integration"],
}

PROJECT_STATUSES = {"planned", "active", "completed", "archived"}
MESSAGE_ROLES = {"user", "assistant", "system"}
MEMORY_TYPES = {"conversation", "goal", "project", "decision", "file", "research"}
