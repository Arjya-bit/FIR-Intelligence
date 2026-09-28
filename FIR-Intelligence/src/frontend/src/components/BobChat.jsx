import { useState, useRef, useEffect } from 'react';
import { api } from '../utils/api';

const SUGGESTED_QUERIES = [
  "Show me all repeat offenders in Lucknow",
  "What crime networks are active in UP?",
  "Which station has the highest crime rate?",
  "Tell me about the Jamtara cyber fraud network",
  "What is Bablu's crime history?",
  "Show drug trafficking patterns",
  "Generate an intelligence brief for Kanpur burglaries",
  "Which districts need immediate police attention?",
];

export default function BobChat() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: "I'm Bob, your AI-powered FIR Intelligence Assistant. I have analyzed 25 FIRs across 7 districts of Uttar Pradesh and identified multiple repeat offenders and organized crime networks.\n\nI can help you with:\n- Crime pattern analysis across districts\n- Repeat offender identification and tracking\n- Station-level crime trends\n- MO signature matching\n- Intelligence report generation\n\nWhat would you like to know?",
    }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async (text) => {
    const msg = text || input.trim();
    if (!msg || loading) return;

    setMessages(prev => [...prev, { role: 'user', content: msg }]);
    setInput('');
    setLoading(true);

    try {
      const res = await api.chat(msg);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: res.response,
        firs: res.firs_referenced,
      }]);
    } catch (e) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Error: ${e.message}. Make sure the backend server is running.`,
      }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="animate-fade-in flex flex-col" style={{ height: 'calc(100vh - 120px)' }}>
      <div className="glass-card p-4 mb-3 glow-blue">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-white text-sm font-bold">B</div>
          <div>
            <h2 className="text-lg font-semibold text-white">Bob AI Intelligence Chat</h2>
            <p className="text-xs text-slate-400">Powered by IBM watsonx.ai Granite &middot; Query FIR intelligence in natural language</p>
          </div>
          <span className="ml-auto text-xs px-2 py-0.5 rounded-full bg-green-900/50 text-green-400 border border-green-800">Online</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto space-y-3 mb-3">
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[80%] rounded-xl px-4 py-3 ${
              msg.role === 'user'
                ? 'bg-blue-600 text-white'
                : 'glass-card text-slate-300'
            }`}>
              <pre className="text-sm whitespace-pre-wrap font-sans">{msg.content}</pre>
              {msg.firs && msg.firs.length > 0 && (
                <div className="mt-2 pt-2 border-t border-slate-600/50">
                  <span className="text-xs text-slate-500">Referenced FIRs: </span>
                  {msg.firs.map((fir, j) => (
                    <span key={j} className="text-xs text-blue-400 mr-1">{fir}</span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="glass-card px-4 py-3 rounded-xl">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
                <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
                <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
              </div>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="mb-2 flex flex-wrap gap-1.5">
        {SUGGESTED_QUERIES.map((q, i) => (
          <button
            key={i}
            onClick={() => sendMessage(q)}
            className="text-xs px-3 py-1.5 rounded-full bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-slate-200 transition-colors border border-slate-700"
          >
            {q}
          </button>
        ))}
      </div>

      <div className="glass-card p-3">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && sendMessage()}
            placeholder="Ask Bob about FIR patterns, offenders, trends..."
            className="flex-1 bg-slate-800/50 text-white text-sm rounded-lg px-4 py-2.5 border border-slate-600 focus:border-blue-500 focus:outline-none"
            disabled={loading}
          />
          <button
            onClick={() => sendMessage()}
            disabled={loading || !input.trim()}
            className="px-5 py-2.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
