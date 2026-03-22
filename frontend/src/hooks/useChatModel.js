import { useState, useEffect, useRef } from 'react';
import { PROVIDERS, MODELS } from '../config/models';

export function useChatModel(initialProvider = 'local', initialModel = 'qwen2.5-coder:7b', { initialMessages = [], onMessagesChange } = {}) {
  const [messages, setMessages] = useState(initialMessages);
  const [isLoading, setIsLoading] = useState(false);
  
  const [activeProvider, setActiveProvider] = useState(initialProvider);
  const [activeModel, setActiveModel] = useState(initialModel);
  const onMessagesChangeRef = useRef(onMessagesChange);
  onMessagesChangeRef.current = onMessagesChange;

  // Notify parent when messages change (for persistence)
  useEffect(() => {
    if (onMessagesChangeRef.current) {
      onMessagesChangeRef.current(messages);
    }
  }, [messages]);

  // Allow loading a different conversation's messages
  const loadMessages = (newMessages) => {
    setMessages(newMessages);
  };

  const appendMessage = (message) => {
    setMessages(prev => [...prev, message]);
  };

  const sendMessage = async (userMessage, { skipCompletion = false } = {}) => {
    const userMsg = { role: 'user', content: userMessage };
    setMessages(prev => [...prev, userMsg]);
    if (skipCompletion) return;
    setIsLoading(true);

    try {
      const providerConfig = PROVIDERS[activeProvider];
      if (!providerConfig) {
        throw new Error(`Unknown provider: ${activeProvider}`);
      }

      // Check API Key unless it's a local model
      let apiKey = null;
      if (providerConfig.envKey) {
        apiKey = import.meta.env[providerConfig.envKey];
        if (!apiKey) {
          throw new Error(`Missing ${providerConfig.envKey} in .env file. Please check your configuration.`);
        }
      }

      // Build conversation history
      const conversationHistory = [...messages, userMsg].map(msg => ({
        role: msg.role,
        content: msg.content
      }));

      let apiResponse;

      if (providerConfig.format === 'openai') {
        // OpenAI-compatible format (OpenAI, Groq, Local/Ollama)
        const response = await fetch(providerConfig.apiEndpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(apiKey && { 'Authorization': `Bearer ${apiKey}` }),
          },
          body: JSON.stringify({
            model: activeModel,
            messages: conversationHistory,
            temperature: 0.7,
            ...(activeProvider !== 'openai' && { max_tokens: 1024 }),
          }),
        });
        
        const data = await response.json();

        if (!response.ok) {
          throw new Error(data.error?.message || `Request failed with status ${response.status}`);
        }

        apiResponse = data.choices?.[0]?.message?.content || '(no reply)';

      } else if (providerConfig.format === 'anthropic') {
         const claudeMessages = conversationHistory.filter(m => m.role !== 'system');
         
         const response = await fetch(providerConfig.apiEndpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'x-api-key': apiKey,
            'anthropic-version': '2023-06-01',
          },
          body: JSON.stringify({
            model: activeModel,
            messages: claudeMessages,
            max_tokens: 1024,
            temperature: 0.7,
          }),
        });

        const data = await response.json();

        if (!response.ok) {
          throw new Error(data.error?.message || `Request failed with status ${response.status}`);
        }

        apiResponse = data.content?.[0]?.text || '(no reply)';
      }

      const aiMsg = { role: 'assistant', content: apiResponse };
      setMessages(prev => [...prev, aiMsg]);

    } catch (err) {
      // Format error message
      const errorContent = err.message.includes('Rate limit') || err.message.includes('quota')
        ? err.message 
        : `❌ Error: ${err.message}`;
      
      setMessages(prev => [...prev, { role: 'assistant', content: errorContent }]);
    }

    setIsLoading(false);
  };

  return {
    messages,
    sendMessage,
    appendMessage,
    loadMessages,
    isLoading,
    activeProvider,
    setActiveProvider,
    activeModel,
    setActiveModel
  };
}
