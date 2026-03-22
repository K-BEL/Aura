export const PROVIDERS = {
  groq: {
    id: 'groq',
    name: 'Groq',
    apiEndpoint: 'https://api.groq.com/openai/v1/chat/completions',
    envKey: 'VITE_GROQ_API_KEY',
    format: 'openai', // Uses OpenAI compatible API format
  },
  openai: {
    id: 'openai',
    name: 'OpenAI',
    apiEndpoint: 'https://api.openai.com/v1/chat/completions',
    envKey: 'VITE_OPENAI_API_KEY',
    format: 'openai',
  },
  anthropic: {
    id: 'anthropic',
    name: 'Anthropic',
    apiEndpoint: 'https://api.anthropic.com/v1/messages',
    envKey: 'VITE_ANTHROPIC_API_KEY',
    format: 'anthropic', // Uses custom Anthropic format
  },
  local: {
    id: 'local',
    name: 'Local (Ollama)',
    apiEndpoint: 'http://localhost:11434/v1/chat/completions',
    envKey: null, // No key needed usually for local
    format: 'openai', // Ollama supports OpenAI API compatible format
  }
};

export const MODELS = {
  groq: [
    { id: 'llama-3.3-70b-versatile', name: 'Llama 3.3 70B Versatile' }
  ],
  openai: [
    { id: 'gpt-4o', name: 'GPT-4o' },
    { id: 'gpt-4-turbo', name: 'GPT-4 Turbo' },
    { id: 'gpt-3.5-turbo', name: 'GPT-3.5 Turbo' }
  ],
  anthropic: [
    { id: 'claude-3-opus-20240229', name: 'Claude 3 Opus' },
    { id: 'claude-3-sonnet-20240229', name: 'Claude 3 Sonnet' },
    { id: 'claude-3-haiku-20240307', name: 'Claude 3 Haiku' }
  ],
  local: [
    { id: 'qwen2.5-coder:7b', name: 'Qwen 2.5 Coder 7B (Local)' }
  ]
};
